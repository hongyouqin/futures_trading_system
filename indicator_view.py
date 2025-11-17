import argparse
import logging
from logging.handlers import TimedRotatingFileHandler
import os
import akshare as ak

import numpy as np
import pandas as pd
from sql.future_data_manager import FuturesDataManager
from custom_indicators.force_indicator import ForceIndex
from custom_indicators.dynamic_value_channel import DynamicValueChannel
import backtrader as bt


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
    

class TestStrategy(bt.Strategy):
    
    params = (
        ('fast', 13), 
        ('slow', 34),
        ('channel_coeff', 0.152579),
        ('channel_window', 60),
    )
    
    def __init__(self):
        # 技术指标
        self.force_index = ForceIndex(self.data, period=2)
        self.force_index13 = ForceIndex(self.data, period=13)
        self.sma_fast = bt.indicators.EMA(period=self.p.fast)
        
        # 动态价值通道指标 - 这会自动显示在主图上
        self.value_channel = DynamicValueChannel(
            self.data,
            slow_period=self.p.slow,
            channel_window=self.p.channel_window,
            initial_coeff=self.p.channel_coeff
        )
    
    def next(self):
        # 策略逻辑...
        # 价值通道会自动更新，不需要在这里手动更新
        pass


def parse_args():
    '''
        k线图指标绘制
    '''
    parser = argparse.ArgumentParser(  
        description='期货指标分析')
    parser.add_argument('--symbol', default="", required= True, 
                        help="期货商品编号")
    parser.add_argument('--period', default="daily", 
                        help="周期: daily, weekly")
    return parser.parse_args()

def futures_main_weekly_sina(
        daily_df: pd.DataFrame = None,
        symbol: str = "V0",
        start_date: str = "19900101",
        end_date: str = "22220101",
    ) -> pd.DataFrame:
        """
        新浪财经-期货-主力连续周线数据
        基于日线数据聚合计算，或直接调用周线接口
        """
        # 1. 获取日线数据后聚合为周线（通用方法）
        daily_df = daily_df.copy()   
        daily_df["date"] = pd.to_datetime(daily_df["date"])
        daily_df.set_index("date", inplace=True)
            
        # 聚合逻辑：每周一至周五为一周，取首开、最高、最低、尾收、成交量和持仓量总和
        weekly_df = daily_df.resample("W-FRI").agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
            "open_interest": "sum",
        }).dropna()

        
        # 2. 日期筛选
        weekly_df = weekly_df[(weekly_df.index >= pd.to_datetime(start_date)) & 
                            (weekly_df.index <= pd.to_datetime(end_date))]
        weekly_df.reset_index(inplace=True)
        weekly_df.rename(columns={"index": "日期"}, inplace=True)
        return weekly_df


if __name__ == '__main__':
    init_logging()
    
    args = parse_args()
    
    symbol = args.symbol
    period = args.period
    tart_date='2024-01-01'
    
    end_date='2025-12-31'
    
    fdm = FuturesDataManager()
    daily_df = fdm.query_data(symbol=symbol, start_date= tart_date, end_date= end_date)
    print(daily_df)
    data_df = daily_df
    if period == 'weekly': 
        print("周线===============")
        week_start_date = '2020-01-01'
        weekly_df = futures_main_weekly_sina(daily_df=data_df.copy(), symbol=symbol, start_date=week_start_date, end_date = end_date)
        data_df = weekly_df
        
    print(data_df.head())
    cerebro = bt.Cerebro()
    # 添加策略
    cerebro.addstrategy(TestStrategy)
    
    # 准备数据 - 确保日期格式正确
    df = data_df.copy()
    df['date'] = pd.to_datetime(df['date'])
    df = df.set_index('date') 
    df = df.sort_index()  # 按时间排序
    
    data = bt.feeds.PandasData(
        dataname=df,
        open='open',
        high='high',
        low='low',
        close='close',
        volume='volume',
        openinterest=None
    )
    
    # 添加数据到Cerebro
    cerebro.adddata(data)
    
    # 设置初始资金
    cerebro.broker.setcash(100000.0)
    
    print('初始资金: %.2f' % cerebro.broker.getvalue())
    print('开始回测...')
    
    # 运行回测
    results = cerebro.run()
    
    # 绘制图表 - 使用更兼容的方式
    cerebro.plot(style='candle', volume=True, barup='red', bardown='green')
