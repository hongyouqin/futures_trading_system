from venv import logger
from pybroker import ExecContext, FeeMode, Strategy, YFinance, indicator
from sql.future_data_manager import FuturesDataManager
from sql.futures_data_source import FuturesDataSource
import pandas as pd
import numpy as np
import pybroker as pb

# 定义指标函数，使用更稳健的计算方式
def short_ma(data):
    return pd.Series(data.close).rolling(window=13).mean().fillna(method='bfill').values

def long_ma(data):
    return pd.Series(data.close).rolling(window=34).mean().fillna(method='bfill').values


# 注册指标
short_ma_ind = indicator('short_ma', short_ma)
long_ma_ind = indicator('long_ma', long_ma)

def dual_ma_trend(close, short_ma_val, long_ma_val):
    '''
        收盘价在双均线上方且均线多头排列
    '''
    cur_close = close[-1]
    fast_ma = short_ma_val[-1]  # 13周均线
    slow_ma = long_ma_val[-1]  # 34周均线
        
    up_trend_cond = all([cur_close > fast_ma, cur_close > slow_ma] ) 
    down_trend_cond = all([cur_close < fast_ma, cur_close < slow_ma])
    if up_trend_cond: 
        return 1
    elif down_trend_cond:
        return -1
    else:
        return 0

# 执行函数：优化后的做多逻辑
def futures_exec_fn(ctx: ExecContext):
    # 获取指标值
    short_ma_val = ctx.indicator('short_ma')
    long_ma_val = ctx.indicator('long_ma')
    close = ctx.close
    
    # 检查是否有足够的数据（至少需要最长均线周期的数据）
    if len(close) < 45:  # 与最长均线周期一致
        return
    
    # 检查是否有NaN值
    if np.isnan(short_ma_val[-1]) or np.isnan(long_ma_val[-1]):
        return
    
    trend = dual_ma_trend(close=close, short_ma_val=short_ma_val, long_ma_val=long_ma_val)    
    # 获取当前持仓
    long_pos = ctx.long_pos()
    short_pos = ctx.short_pos()

    # 做多信号
    if trend == 1:
        if short_pos:  # 如果当前有空头持仓，先平空
            ctx.sell_shares = abs(short_pos.shares)
            logger.debug(f"{ctx.symbol} 平空仓开多仓, 价格: {close[-1]:.2f}")
        elif not long_pos:  # 如果没有多头持仓，开多
            ctx.buy_shares = 1
            logger.debug(f"{ctx.symbol} 开多仓, 价格: {close[-1]:.2f}")
    
    # 做空信号
    elif trend == -1:
        if long_pos:  # 如果当前有多头持仓，先平多
            ctx.sell_shares = long_pos.shares
            logger.debug(f"{ctx.symbol} 平多仓开空仓, 价格: {close[-1]:.2f}")
        elif not short_pos:  # 如果没有空头持仓，开空
            ctx.sell_shares = -1  # 负数表示开空仓
            logger.debug(f"{ctx.symbol} 开空仓, 价格: {close[-1]:.2f}")
    
    # 震荡市平仓信号
    elif trend == 0:
        if long_pos:
            ctx.sell_shares = long_pos.shares
            logger.debug(f"{ctx.symbol} 平多仓(震荡市), 价格: {close[-1]:.2f}")
        elif short_pos:
            ctx.sell_shares = abs(short_pos.shares)
            logger.debug(f"{ctx.symbol} 平空仓(震荡市), 价格: {close[-1]:.2f}")

def run_futures_backtest():
    """运行期货回测"""
    
    # 初始化数据管理器
    fdm = FuturesDataManager()
    
    # 获取所有活跃的主力合约
    active_contracts = fdm.get_active_main_contracts()
    if not active_contracts:
        logger.info("更新主力合约列表...")
        fdm.update_main_contract_list()
        active_contracts = fdm.get_active_main_contracts()
    
    logger.info(f"找到{len(active_contracts)}个活跃合约")
    
    # 选择要测试的合约（可以根据需要修改）
    test_symbols = active_contracts[:10]  # 测试前10个合约
    # 或者手动指定特定品种
    # test_symbols = ['IF0', 'IC0', 'IH0', 'AU0', 'AG0', 'CU0', 'AL0', 'ZN0', 'PB0', 'NI0']
    
    logger.info(f"测试合约: {test_symbols}")
    
    # 创建期货数据源
    futures_data_source = FuturesDataSource(fdm, test_symbols)
    
    # 初始化策略
    my_config = pb.StrategyConfig(
            initial_cash=500000,
            # 手续费设置
            fee_mode=FeeMode.ORDER_PERCENT,  # 按订单金额百分比计算手续费
            fee_amount=0.0003,  # 万分之三的手续费
            subtract_fees=True,  # 从现金余额中扣除手续费
            enable_fractional_shares=False,  # 期货不支持分数股
            # 其他设置
            buy_delay=1,
            sell_delay=1,
            bars_per_year=252,  # 年化计算使用252个交易日
            exit_on_last_bar=True  # 在最后一天自动平仓
        )
    
    strategy = Strategy(
        futures_data_source,
        start_date='2015-01-01',
        end_date='2025-09-18',  # 使用实际数据日期
        config=my_config
    )
    
    # 添加执行函数和指标
    strategy.add_execution(
        futures_exec_fn,
        symbols=test_symbols,
        indicators=[short_ma_ind, long_ma_ind]
    )
    
    # 运行回测
    try:
        logger.info("开始期货回测...")
        result = strategy.backtest(warmup=45)
        
        # 输出结果
        print("\n" + "="*50)
        print("期货双均线策略回测结果")
        print("="*50)
        print(result.metrics_df.round(4))
        
        # 额外输出每个品种的表现
        print("\n各品种表现:")
        for symbol in test_symbols:
            symbol_result = result.get_symbol_results(symbol)
            if symbol_result and not symbol_result.trades.empty:
                trades = symbol_result.trades
                win_rate = len(trades[trades['pnl'] > 0]) / len(trades) * 100
                total_pnl = trades['pnl'].sum()
                print(f"{symbol}: 交易次数{len(trades)}, 胜率{win_rate:.1f}%, 总盈亏{total_pnl:.2f}")
        
        return result
        
    except Exception as e:
        logger.error(f"回测失败: {e}")
        return None


# 测试单个合约的双向交易
def test_single_contract_with_short():
    """测试单个合约的做空功能"""
    fdm = FuturesDataManager()
    
    test_symbol = 'IF0'  # 沪深300主力合约
    
    # 检查数据
    data = fdm.query_data(symbol=test_symbol, start_date="2023-01-03", end_date="2024-09-18")
    if data.empty:
        print(f"{test_symbol} 数据为空，正在更新数据...")
        fdm.update_main_contract_list()
        contract_data = fdm.fetch_main_contract_data(test_symbol, "20200101")
        if not contract_data.empty:
            fdm.save_to_database(contract_data)
    
    # 创建数据源
    futures_data_source = FuturesDataSource(fdm, [test_symbol])
    
    # 配置支持双向交易
    my_config = pb.StrategyConfig(
        initial_cash=500000,
        fee_mode=FeeMode.ORDER_PERCENT,
        fee_amount=0.0003,
        subtract_fees=True,
        enable_fractional_shares=False,
        max_long_positions=1,
        max_short_positions=1,
        buy_delay=1,
        sell_delay=1,
        bars_per_year=252,
        exit_on_last_bar=True
    )
    
    strategy = Strategy(
        futures_data_source,
        start_date='2020-01-01',
        end_date='2024-09-18',
        config=my_config
    )
    
    strategy.add_execution(
        futures_exec_fn,
        symbols=[test_symbol],
        indicators=[short_ma_ind, long_ma_ind]
    )
    
    # 运行回测
    result = strategy.backtest(warmup=45)
    
    print(f"\n{test_symbol} 双向交易回测结果:")
    print(result.metrics_df.round(4))
    
    # 输出交易详情
    if not result.orders.empty:
        print("\n交易订单详情:")
        print(result.orders.tail(20))

# 初始化策略（使用实际已有的数据范围）
# my_config = pb.StrategyConfig(initial_cash=500000)
# strategy = Strategy(
#     YFinance(),
#     start_date='2020-01-01',
#     end_date='2025-12-31',  # 只使用已完成的年份数据,
#     config=my_config
# )

# # 添加执行函数和指标
# strategy.add_execution(
#     futures_exec_fn,
#     symbols=['000831.SZ'],  # 中国稀土
#     indicators=[short_ma_ind, long_ma_ind]
# )

# # 运行回测
# result = strategy.backtest(warmup=45)  # 预热期与最长均线周期一致
# print(result.metrics_df.round(4))



