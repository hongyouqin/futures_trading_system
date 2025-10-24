# 导入所需的库和模块
import pybroker as pb
from pybroker import Strategy, ExecContext
from pybroker.ext.data import AKShare



'''
指标解释：

一、账户价值与盈亏
trade_count (373)：总交易次数

initial_market_value (500,000)：初始资金50万

end_market_value (467,328.09)：期末市值，亏损至约46.7万

total_pnl (-33,322.78)：总盈亏，亏损约3.3万

unrealized_pnl (650.87)：未实现盈亏（持仓浮盈）

total_return_pct (-6.66%)：总收益率 -6.66%

二、盈利质量指标
total_profit (530,528.51)：所有盈利交易的总利润

total_loss (-563,851.29)：所有亏损交易的总损失

win_rate (45.92%)：胜率，不到一半交易盈利

loss_rate (54.08%)：亏损率

winning_trades (152)：盈利交易次数

losing_trades (179)：亏损交易次数

三、平均表现
avg_pnl (-89.34)：平均每笔交易亏损89元

avg_return_pct (-0.016%)：平均每笔交易收益率

avg_profit (3,490.32)：盈利交易的平均利润

avg_loss (-3,150.01)：亏损交易的平均损失

profit_factor (0.96)：盈利因子 = 总盈利/总亏损 < 1，策略不盈利

四、风险指标
max_drawdown (-113,004.27)：最大回撤金额

max_drawdown_pct (-20.27%)：最大回撤比例，资金曾从高点回撤20%

sharpe (-0.0107)：夏普比率，负值表示风险调整后收益为负

sortino (-0.0193)：索提诺比率，同样为负

ulcer_index (1.76)：溃疡指数，衡量下跌风险和持续时间

五、交易特征
avg_trade_bars (1.0)：平均持仓周期（K线数），显示为短线交易

largest_win (31,157.94)：最大单笔盈利

largest_loss (-12,682.6)：最大单笔亏损

'''

# 定义全局参数 "stock_code"（股票代码）、"percent"（持仓百分比）和 "stop_profit_pct"（止盈百分比）
pb.param(name='stock_code', value='600000')
pb.param(name='percent', value=1)
pb.param(name='stop_loss_pct', value=10)
pb.param(name='stop_profit_pct', value=10)

# 初始化 AKShare 数据源
akshare = AKShare()

# 使用 AKShare 数据源查询特定股票（由 "stock_code" 参数指定）在指定日期范围内的数据
akshare.query(symbols=[pb.param(name='stock_code')], start_date='20200131', end_date='20230228')


# 定义交易策略：如果当前没有持有该股票，则买入股票，并设置止盈点位
def buy_with_stop_loss(ctx: ExecContext):
    pos = ctx.long_pos()
    if not pos:
        # 计算目标股票数量，根据 "percent" 参数确定应购买的股票数量
        ctx.buy_shares = ctx.calc_target_shares(pb.param(name='percent'))
        ctx.hold_bars = 100
    else:
        ctx.sell_shares = pos.shares
        # 设置止盈点位，根据 "stop_profit_pct" 参数确定止盈点位
        ctx.stop_profit_pct = pb.param(name='stop_profit_pct')


# 创建策略配置，初始资金为 500000
my_config = pb.StrategyConfig(initial_cash=500000)
# 使用配置、数据源、起始日期、结束日期，以及刚才定义的交易策略创建策略对象
strategy = Strategy(akshare, start_date='20200131', end_date='20230228', config=my_config)
# 添加执行策略，设置股票代码和要执行的函数
strategy.add_execution(fn=buy_with_stop_loss, symbols=[pb.param(name='stock_code')])
# 执行回测，并打印出回测结果的度量值（四舍五入到小数点后四位）
result = strategy.backtest()
print(result.metrics_df.round(4))
