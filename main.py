from __future__ import annotations

import argparse
import logging
import sys

from dotenv import load_dotenv

from config import Settings
from mve import MVEAutomationClient, MVEFatalError
from sheets import GoogleSheetRepository
from workflow import PatientProfileWorkflow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Process pending Google Sheet rows into MVE patient profiles."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Override the per-run batch size.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set the application log level.",
    )
    return parser


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main() -> int:
    load_dotenv()
    args = build_parser().parse_args()
    configure_logging(args.log_level)

    settings = Settings.from_env()
    logger = logging.getLogger("mve_patient_agent")

    try:
        sheet_repository = GoogleSheetRepository(settings)
        mve_client = MVEAutomationClient(settings)
        workflow = PatientProfileWorkflow(settings, sheet_repository, mve_client)
        summary = workflow.run(limit=args.limit)
    except MVEFatalError as exc:
        logger.error("Fatal MVE automation error: %s", exc)
        return 1
    except Exception as exc:  # pragma: no cover - operational fallback
        logger.exception("Unhandled application error: %s", exc)
        return 1

    logger.info(
        "Run completed. processed=%s updated=%s skipped=%s failed=%s",
        summary.processed,
        summary.updated,
        summary.skipped,
        summary.failed,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
