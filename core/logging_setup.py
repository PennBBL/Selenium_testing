import logging
import sys
from datetime import datetime
from pathlib import Path


def setup_logging(output_dir: Path, name: str = 'battery_runner') -> logging.Logger:
    output_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    log_file = output_dir / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    fh = logging.FileHandler(log_file, mode='w', encoding='utf-8')
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    logger.info(f'Logging to {log_file}')
    return logger
