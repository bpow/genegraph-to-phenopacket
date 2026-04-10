import sys
import logging
from gci_phenopacket.utils.logger import setup_logger


def test_logger_returns_logger_instance():
    logger = setup_logger()
    assert isinstance(logger, logging.Logger)


def test_logger_has_stdout_handler():
    logger = setup_logger()
    stream_handlers = [h for h in logger.handlers if isinstance(h, logging.StreamHandler)]
    assert len(stream_handlers) > 0


def test_logger_has_no_file_handler():
    logger = setup_logger()
    file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
    assert len(file_handlers) == 0
