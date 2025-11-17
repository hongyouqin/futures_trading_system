import os
import logging
from logging.handlers import TimedRotatingFileHandler
# from pybroker import YFinance

from my_backtrader.dual_ma_strategy import run_backtest, batch_backtest

# yfinance = YFinance()
# df = yfinance.query(['AAPL', 'MSFT'], start_date='3/1/2021', end_date='3/1/2022')
# df


def init_logging():
    """全局日志配置（在策略初始化前调用）"""
    log_format = '%(asctime)s [%(levelname)s] %(message)s'
    log_file = 'logs/futures.log'
    
    # 创建日志目录
    os.makedirs('logs', exist_ok=True)
    
    # 主日志配置
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            TimedRotatingFileHandler(
                log_file, 
                when='D',  # 按天切割
                backupCount=7,
                encoding='utf-8'
            ),
            logging.StreamHandler()
        ]
    )
    


if __name__ == '__main__':
    init_logging()
    
    # 回测参数
    SYMBOL = "FG0"  # 主力合约
    START_DATE = "2020-01-01"
    END_DATE = "2025-12-31"
    DB_PATH = "E:\\db\\futures_data.db"  # 你的数据库路径


    # 运行回测
    result = run_backtest(
        symbol=SYMBOL, 
        start_date=START_DATE,
        end_date=END_DATE,
        db_path=DB_PATH,
        display= False
    )
    
    print("===============结果报告===============")
    print(result)
    
    