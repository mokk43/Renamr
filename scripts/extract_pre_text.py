#!/usr/bin/env python3
"""Fetch sequential pages and extract target DOM text into an output file.

Usage:
    python scripts/extract_pre_text.py "https://example.com/page?book=10" 5
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_FETCH_INTERVAL_SECONDS = 3.0
DEFAULT_OUTPUT_FILE = "output.txt"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_RETRY_TOTAL = 3
DEFAULT_RETRY_BACKOFF_SECONDS = 1.0
DEFAULT_LOG_FILE = "extract_pre_text.log"

# First selector is what the user requested. Second matches screenshot classes/ids.
DEFAULT_SELECTORS = (
    "#main-content > #post-content > #content-section > pre",
    ".main-content > .post-content > #content-section > pre",
    "body > table > tbody > tr > td > pre > p",
    "body table tbody tr td pre p",
    "td.show_content pre > p",
    "td.show_content pre",
)


def setup_logger(log_file: str) -> logging.Logger:
    """Create a logger that writes to console and file."""
    logger = logging.getLogger("extract_pre_text")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def sanitize_filename(name: str) -> str:
    """Sanitize a string for cross-platform filename safety."""
    cleaned = "".join("_" if c in '<>:"/\\|?*\n\r\t' else c for c in name).strip()
    return cleaned.rstrip(". ") or "output"


def derive_output_path_from_text(
    extracted_text: str, output_dir: Path, fallback_name: str = DEFAULT_OUTPUT_FILE
) -> Path:
    """Build unique output path using first line of extracted text."""
    first_non_empty_line = next(
        (line.strip() for line in extracted_text.splitlines() if line.strip()),
        "",
    )
    if not first_non_empty_line:
        stem = Path(fallback_name).stem
    else:
        stem = sanitize_filename(first_non_empty_line)
    candidate = output_dir / f"{stem}.txt"
    if not candidate.exists():
        return candidate

    index = 1
    while True:
        numbered = output_dir / f"{stem}_{index}.txt"
        if not numbered.exists():
            return numbered
        index += 1


def build_session_with_retries(retry_total: int, retry_backoff_seconds: float) -> requests.Session:
    """Build a requests session with retry support for transient failures."""
    retry = Retry(
        total=retry_total,
        connect=retry_total,
        read=retry_total,
        status=retry_total,
        backoff_factor=retry_backoff_seconds,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)

    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def build_url_with_incremented_param(
    base_url: str, offset: int, param_name: str | None
) -> str:
    """Return URL where numeric query parameter value is increased by offset.

    If param_name is provided, increment that parameter.
    Otherwise increment the last query parameter.
    """
    parts = urlsplit(base_url)
    pairs = parse_qsl(parts.query, keep_blank_values=True)

    if not pairs:
        raise ValueError("URL must include at least one query parameter.")

    target_index = len(pairs) - 1
    if param_name:
        matched_index = next((i for i, (k, _) in enumerate(pairs) if k == param_name), None)
        if matched_index is None:
            available = ", ".join(k for k, _ in pairs)
            raise ValueError(
                f"Query parameter '{param_name}' not found in URL. Available: {available}"
            )
        target_index = matched_index

    key, value = pairs[target_index]
    try:
        number = int(value)
    except ValueError as exc:
        hint = f"parameter '{key}'"
        if param_name:
            hint = f"parameter '{param_name}'"
        raise ValueError(
            f"The selected query {hint} must be an integer, got '{value}'."
        ) from exc

    pairs[target_index] = (key, str(number + offset))
    new_query = urlencode(pairs, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


def build_url_with_replaced_param(
    base_url: str, replacement_value: int, param_name: str | None
) -> str:
    """Return URL where selected query parameter is replaced by replacement_value."""
    parts = urlsplit(base_url)
    pairs = parse_qsl(parts.query, keep_blank_values=True)

    if not pairs:
        raise ValueError("URL must include at least one query parameter.")

    target_index = len(pairs) - 1
    if param_name:
        matched_index = next((i for i, (k, _) in enumerate(pairs) if k == param_name), None)
        if matched_index is None:
            available = ", ".join(k for k, _ in pairs)
            raise ValueError(
                f"Query parameter '{param_name}' not found in URL. Available: {available}"
            )
        target_index = matched_index

    key, _ = pairs[target_index]
    pairs[target_index] = (key, str(replacement_value))
    new_query = urlencode(pairs, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


def extract_text_by_selectors(html: str, selectors: tuple[str, ...]) -> str:
    """Extract text from all matches of the first selector that has any match."""
    soup = BeautifulSoup(html, "html.parser")
    for selector in selectors:
        nodes = soup.select(selector)
        if nodes:
            texts = [node.get_text("\n", strip=False) for node in nodes]
            return "\n".join(texts)
    raise ValueError("Target element not found with selectors: " + ", ".join(selectors))


def parse_selector_list(raw_selector: str) -> tuple[str, ...]:
    """Parse comma-separated selectors into a validated tuple."""
    selectors = tuple(part.strip() for part in raw_selector.split(",") if part.strip())
    if not selectors:
        return DEFAULT_SELECTORS
    return selectors


def parse_page_spec(raw: str) -> tuple[str, int | list[int]]:
    """Parse second CLI parameter as either count or comma-separated number list."""
    cleaned = raw.strip()
    if not cleaned:
        raise ValueError("parameter2 must not be empty.")

    if "," in cleaned:
        parts = [part.strip() for part in cleaned.split(",")]
        if any(not part for part in parts):
            raise ValueError("parameter2 list contains an empty item.")
        try:
            numbers = [int(part) for part in parts]
        except ValueError as exc:
            raise ValueError("parameter2 list must contain only integers.") from exc
        return ("list", numbers)

    try:
        count = int(cleaned)
    except ValueError as exc:
        raise ValueError(
            "parameter2 must be either an integer count or comma-separated integers."
        ) from exc
    return ("count", count)


def fetch_page_text(
    session: requests.Session,
    url: str,
    timeout_seconds: float,
    selectors: tuple[str, ...],
) -> str:
    """Fetch one page and extract text using selectors."""
    response = session.get(url, timeout=timeout_seconds)
    response.raise_for_status()
    if not response.encoding or response.encoding.lower() == "iso-8859-1":
        response.encoding = response.apparent_encoding
    return extract_text_by_selectors(response.text, selectors)


def fetch_pages(
    start_url: str,
    page_mode: str,
    page_values: int | list[int],
    output_dir: Path,
    selectors: tuple[str, ...],
    interval_seconds: float,
    timeout_seconds: float,
    param_name: str | None,
    retry_total: int,
    retry_backoff_seconds: float,
    logger: logging.Logger,
) -> None:
    """Fetch pages by count mode or explicit list mode, then write in one run."""
    session = build_session_with_retries(
        retry_total=retry_total,
        retry_backoff_seconds=retry_backoff_seconds,
    )
    fetch_urls: list[str] = []
    if page_mode == "count":
        page_count = int(page_values)
        fetch_urls = [
            build_url_with_incremented_param(start_url, index, param_name)
            for index in range(page_count)
        ]
    else:
        explicit_values = list(page_values)
        fetch_urls.append(start_url)
        for number in explicit_values:
            fetch_urls.append(build_url_with_replaced_param(start_url, number, param_name))

    output_path: Path | None = None
    out = None
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        total = len(fetch_urls)
        for index, page_url in enumerate(fetch_urls):
            logger.info("[%s/%s] Fetching URL: %s", index + 1, total, page_url)
            text = fetch_page_text(session, page_url, timeout_seconds, selectors)

            if out is None:
                output_path = derive_output_path_from_text(text, output_dir)
                out = output_path.open("w", encoding="utf-8")
                logger.info("Session output file created: %s", output_path)

            out.write(text)
            out.write("\n\n")
            out.flush()
            logger.info("[%s/%s] Extracted text and written to %s", index + 1, total, output_path)

            if index < total - 1 and interval_seconds > 0:
                logger.info("[%s/%s] Sleeping %.2fs after fetch", index + 1, total, interval_seconds)
                time.sleep(interval_seconds)
    finally:
        if out is not None:
            out.close()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch sequential pages and append text from target DOM selector(s) to output"
        )
    )
    parser.add_argument("start_url", help="First page URL")
    parser.add_argument(
        "page_spec",
        help=(
            "Either total count (e.g. 5) for successive fetches, "
            "or comma-separated numbers (e.g. 10,15,22) for explicit replacements"
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Output directory for generated .txt file (default: current directory)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_FETCH_INTERVAL_SECONDS,
        help=f"Seconds to sleep after each fetch (default: {DEFAULT_FETCH_INTERVAL_SECONDS})",
    )
    parser.add_argument(
        "--selector",
        default=",".join(DEFAULT_SELECTORS),
        help=(
            "CSS selector(s), comma-separated. First matching selector is used "
            f"(default: {','.join(DEFAULT_SELECTORS)})"
        ),
    )
    parser.add_argument(
        "--param-name",
        default="",
        help="Query parameter name to increment (default: increment last query parameter)",
    )
    parser.add_argument(
        "--log-file",
        default=DEFAULT_LOG_FILE,
        help=f"Log file path (default: {DEFAULT_LOG_FILE})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"HTTP timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS})",
    )
    parser.add_argument(
        "--retry-total",
        type=int,
        default=DEFAULT_RETRY_TOTAL,
        help=f"Total retries for transient request failures (default: {DEFAULT_RETRY_TOTAL})",
    )
    parser.add_argument(
        "--retry-backoff",
        type=float,
        default=DEFAULT_RETRY_BACKOFF_SECONDS,
        help=(
            "Retry backoff factor in seconds; exponential delay is applied by urllib3 "
            f"(default: {DEFAULT_RETRY_BACKOFF_SECONDS})"
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    if args.interval < 0:
        print("--interval must be >= 0", file=sys.stderr)
        return 2
    if args.timeout <= 0:
        print("--timeout must be > 0", file=sys.stderr)
        return 2
    if args.retry_total < 0:
        print("--retry-total must be >= 0", file=sys.stderr)
        return 2
    if args.retry_backoff < 0:
        print("--retry-backoff must be >= 0", file=sys.stderr)
        return 2

    selectors = parse_selector_list(args.selector)
    output_dir = Path(args.output_dir)
    logger = setup_logger(args.log_file)
    param_name = args.param_name.strip() or None
    try:
        page_mode, page_values = parse_page_spec(args.page_spec)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if page_mode == "count" and int(page_values) <= 0:
        print("When parameter2 is a count, it must be > 0", file=sys.stderr)
        return 2

    logger.info(
        "Starting extraction: page_spec=%s, interval=%.2fs, output_dir=%s",
        args.page_spec,
        args.interval,
        output_dir,
    )
    logger.info("Selectors in use: %s", ", ".join(selectors))
    if param_name:
        logger.info("Incrementing query parameter: %s", param_name)
    else:
        logger.info("Incrementing last query parameter")

    try:
        fetch_pages(
            start_url=args.start_url,
            page_mode=page_mode,
            page_values=page_values,
            output_dir=output_dir,
            selectors=selectors,
            interval_seconds=args.interval,
            timeout_seconds=args.timeout,
            param_name=param_name,
            retry_total=args.retry_total,
            retry_backoff_seconds=args.retry_backoff,
            logger=logger,
        )
    except Exception as exc:
        logger.error("Error: %s", exc)
        return 1

    logger.info("Done. Check log entries for the generated output file path.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
