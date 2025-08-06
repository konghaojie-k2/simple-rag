"""日志配置工具"""

import sys
from pathlib import Path
from loguru import logger


def setup_logger(
    log_level: str = "INFO",
    log_file: str = None,
    rotation: str = "10 MB",
    retention: str = "7 days"
):
    """
    配置loguru日志系统
    
    Args:
        log_level: 日志级别
        log_file: 日志文件路径（可选）
        rotation: 日志轮转大小
        retention: 日志保留时间
    """
    # 移除默认handler
    logger.remove()
    
    # 添加控制台handler
    logger.add(
        sys.stdout,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
               "<level>{message}</level>",
        colorize=True
    )
    
    # 如果指定了日志文件，添加文件handler
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.add(
            log_path,
            level=log_level,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
            rotation=rotation,
            retention=retention,
            encoding="utf-8"
        )
    
    return logger


# 创建默认logger实例
rag_logger = setup_logger()