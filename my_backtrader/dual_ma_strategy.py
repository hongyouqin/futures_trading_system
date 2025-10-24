from datetime import datetime
from typing import List
import backtrader as bt
import pandas as pd
import logging
from sql.future_data_manager import FuturesDataManager
from utils.common import classify_symbol, get_parameter_groups

# 确保FuturesDataManager已正确定义
# （此处省略FuturesDataManager类定义，使用你提供的版本即可）

# 配置日志

logger = logging.getLogger('DualMaFuturesStrategy')

class DualMaStrategy(bt.Strategy):
    """双均线期货策略：收盘价在双均线上方且均线多头排列做多，反之做空"""
    params = (
        ('short_ma_period', 13),   # 短期均线周期（周线级别对应13周）
        ('long_ma_period', 34),    # 长期均线周期（周线级别对应34周）
        ('size', 1),               # 每笔交易手数
        ('commission', 0.0001),    # 手续费率
        ('margin', 0.1),           # 保证金比例（10%）
        ('mult', 10),
         ('adx_threshold', 20),    # ADX趋势强度阈值
         ('atr_stop_multiplier', 2), # ATR止损倍数
    )

    def __init__(self):
        self.logger = logging.getLogger('DualMaStrategy')
        
        symbol = self.data._name
        # self.adjust_params = self.adjust_parameters(symbol=symbol)
        # print(f"symbol={symbol} short_period={self.adjust_params['short_ma']} long_period={self.adjust_params['long_ma']}")
        
        self.atr = bt.indicators.ATR(self.data, period=14)
        dmi = bt.indicators.DirectionalMovementIndex(period = 14)
        self.adx = dmi.lines.adx
        
        self.stop_price = None
        self.entry_price = None
        
        # 自动分类并获取对应参数
        symbol_group = classify_symbol(symbol)
        group_params = get_parameter_groups().get(symbol_group, {
            'short_ma': self.params.short_ma_period,
            'long_ma': self.params.long_ma_period
        })
        
        self.short_ma_period = group_params['short_ma']
        self.long_ma_period = group_params['long_ma']
        
        self.logger.info(f"symbol={symbol} short_period={self.short_ma_period} long_period={self.long_ma_period}")
        
        # 初始化均线指标
        self.short_ma = bt.indicators.SMA(
            self.data.close, period=self.short_ma_period, plotname='短期均线'
        )
        self.long_ma = bt.indicators.SMA(
            self.data.close, period=self.long_ma_period, plotname='长期均线'
        )
        
        self.order = None
        self.last_operation = None  # 记录上一次操作类型
        
    # 降低阈值，但增加其他确认条件
    def is_trend_strong_enough(self):
        if len(self.adx) < 2:
            return False
        
        # 基本条件
        basic_condition = self.adx[0] > 20
        
        # 加强条件：ADX上升或价格确认下跌趋势
        strengthening = (self.adx[0] > self.adx[-1]) 
        
        return basic_condition and strengthening
    

    
    def calculate_stop_price(self, is_long: bool):
        """计算基于ATR的止损价格"""
        if len(self.atr) == 0:
            return None
            
        current_atr = self.atr[0]
        stop_distance = current_atr * self.params.atr_stop_multiplier
        
        if is_long:
            # 多头止损：入场价 - ATR * 倍数
            return self.entry_price - stop_distance
        else:
            # 空头止损：入场价 + ATR * 倍数
            return self.entry_price + stop_distance
    
    def stop_loss(self):
        '''
            硬止损
        '''
        if self.position and self.entry_price and self.stop_price:
            if self.position.size > 0:  # 多仓
                if self.data.close[0] < self.stop_price:
                    self.order = self.close()
                    logger.info(f"硬止损平多: {self.data.close[0]:.2f}")
                    return
            else:  # 空仓
                if self.data.close[0] > self.stop_price:
                    self.order = self.close() 
                    logger.info(f"硬止损平空: {self.data.close[0]:.2f}")
                    return
    
    def update_stop_price(self):
        """更新动态止损价格（可用于移动止损）"""
        if self.position and self.entry_price and self.stop_price:
            if self.position.size > 0:  # 多仓
                # 可以在这里实现移动止损逻辑
                # 例如：当价格上涨时，提高止损价格
                new_stop = self.calculate_stop_price(is_long=True)
                if new_stop and new_stop > self.stop_price:
                    self.stop_price = new_stop
                    logger.debug(f"更新多头止损价: {self.stop_price:.2f}")
            else:  # 空仓
                new_stop = self.calculate_stop_price(is_long=False)
                if new_stop and new_stop < self.stop_price:
                    self.stop_price = new_stop
                    logger.debug(f"更新空头止损价: {self.stop_price:.2f}")
    
    def check_margin_sufficient(self, price, size, is_long=True):
        """检查保证金是否足够开仓"""
        # 计算所需保证金
        contract_value = price * size * self.params.mult if hasattr(self.params, 'mult') else price * size
        required_margin = contract_value * self.params.margin
        
        # 获取当前可用资金
        available_cash = self.broker.getcash()
        
        # 对于空头头寸，需要考虑额外的保证金要求
        if not is_long:
            # 空头通常需要更多保证金，这里增加20%的安全边际
            required_margin *= 1.2
        
        margin_sufficient = available_cash >= required_margin
        
        if not margin_sufficient:
            logger.warning(
                f"保证金不足: 需要{required_margin:.2f}, 可用{available_cash:.2f}, "
                f"价格={price:.2f}, 手数={size}"
            )
        
        return margin_sufficient
    
    def next(self):
        if self.order:
            return
        
        self.stop_loss()
        self.update_stop_price()
        
        if not self.is_trend_strong_enough():
            return
        
        # 获取当前价格和均线值
        cur_close = self.data.close[0]
        fast_ma = self.short_ma[0]
        slow_ma = self.long_ma[0]

        # 计算趋势（1: 上涨, -1: 下跌, 0: 盘整）
        up_trend = cur_close > fast_ma and cur_close > slow_ma
        down_trend = cur_close < fast_ma and cur_close < slow_ma

        # 多头信号：没有持仓且趋势上涨
        if not self.position:
            if up_trend and self.last_operation != 'long':
                # 开多仓
                if self.check_margin_sufficient(cur_close, self.params.size, is_long=True):
                    self.order = self.buy(size=self.params.size)
                    self.last_operation = 'long'
                    self.entry_price = cur_close
                    self.stop_price = self.calculate_stop_price(is_long=True)
                    logger.info(
                        f"{self.data.datetime.date(0)} 开多仓: 价格={cur_close:.2f}, "
                        f"短期均线={fast_ma:.2f}, 长期均线={slow_ma:.2f}"
                    )
                else:
                    logger.warning(f"{self.data.datetime.date(0)} 保证金不足，无法开多仓")
                    
            elif down_trend and self.last_operation != 'short':
                # 开空仓
                if self.check_margin_sufficient(cur_close, self.params.size, is_long=False):
                    self.order = self.sell(size=self.params.size)
                    self.entry_price = cur_close
                    self.last_operation = 'short'
                    self.stop_price = self.calculate_stop_price(is_long=False)
                    logger.info(
                        f"{self.data.datetime.date(0)} 开空仓: 价格={cur_close:.2f}, "
                        f"短期均线={fast_ma:.2f}, 长期均线={slow_ma:.2f}"
                    )
                else:
                    logger.warning(f"{self.data.datetime.date(0)} 保证金不足，无法开空仓")
        
        # 有持仓时的反向信号
        elif self.position.size > 0 and down_trend:  # 持多仓时出现空头信号
            self.order = self.close()  # 平多仓
            logger.info(f"{self.data.datetime.date(0)} 平多仓: 价格={cur_close:.2f}")
            
        elif self.position.size < 0 and up_trend:  # 持空仓时出现多头信号
            self.order = self.close()  # 平空仓
            logger.info(f"{self.data.datetime.date(0)} 平空仓: 价格={cur_close:.2f}")

    def notify_order(self, order):
        """订单状态通知（区分平仓和开仓）"""
        if order.status in [order.Submitted, order.Accepted]:
            return  # 忽略未完成订单

        # 订单完成
        if order.status == order.Completed:
            # 判断是平仓还是开仓
            if order.isbuy():
                # 买单：可能是开多单或平空单
                if self.position.size > 0:  # 平仓后持仓为正（开多单）
                    logger.info(
                        f"开多单成交: 价格={order.executed.price:.2f}, "
                        f"手数={order.executed.size}, 手续费={order.executed.comm:.2f}"
                    )
                else:  # 平仓后持仓为0或负（平空单）
                    logger.info(
                        f"平空单成交: 价格={order.executed.price:.2f}, "
                        f"手数={abs(order.executed.size)}, 手续费={order.executed.comm:.2f}"
                    )
            elif order.issell():
                # 卖单：可能是开空单或平多单
                if self.position.size < 0:  # 平仓后持仓为负（开空单）
                    logger.info(
                        f"开空单成交: 价格={order.executed.price:.2f}, "
                        f"手数={abs(order.executed.size)}, 手续费={order.executed.comm:.2f}"
                    )
                else:  # 平仓后持仓为0或正（平多单）
                    logger.info(
                        f"平多单成交: 价格={order.executed.price:.2f}, "
                        f"手数={order.executed.size}, 手续费={order.executed.comm:.2f}"
                    )
            
            # 平仓时重置止损相关变量
            if self.position.size == 0:
                self.entry_price = None
                self.stop_price = None
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            logger.warning(f"订单失败: {order.getstatusname()}")
        
        # 重置订单状态
        self.order = None

    def notify_trade(self, trade):
        """交易状态通知"""
        if not trade.isclosed:
            return

        logger.info(
            f"交易结束: 利润={trade.pnl:.2f}, "
            f"净利润={trade.pnlcomm:.2f}, 持仓周期={trade.barlen}根K线"
        )


class FuturesDataFeed(bt.feeds.PandasData):
    """适配期货数据的Backtrader数据源"""
    params = (
        ('datetime', 'date'),
        ('open', 'open'),
        ('high', 'high'),
        ('low', 'low'),
        ('close', 'close'),
        ('volume', 'volume'),
        ('openinterest', 'open_interest'),
    )


def batch_backtest(symbols: List[str], start_date: str, end_date: str, db_path: str):
    """批量回测多个合约"""
    results = {}
    
    for symbol in symbols:
        logger.info(f"\n{'='*60}")
        logger.info(f"开始回测合约: {symbol}")
        logger.info(f"{'='*60}")
        
        try:
            # 运行单个合约回测
            result = run_backtest(symbol, start_date, end_date, db_path)
            results[symbol] = result
        except Exception as e:
            logger.error(f"回测{symbol}时发生错误: {e}")
            results[symbol] = {'error': str(e)}
    
    # 输出批量回测总结
    # print_batch_summary(results)
    return results

def run_backtest(symbol: str, start_date: str, end_date: str, db_path: str, display: bool = False):
    """运行回测"""
    # 1. 初始化 cerebro
    cerebro = bt.Cerebro()
    
    # 2. 设置初始资金和手续费
    cerebro.broker.setcash(500000.0)  # 初始资金10万元
    cerebro.broker.setcommission(
        commission=0.0001,  # 手续费率
        margin=0.1,         # 保证金比例（10%）
        mult=10,            # 合约乘数（根据实际合约调整）
        commtype=bt.CommInfoBase.COMM_PERC  # 按百分比收费
    )
    cerebro.broker.set_shortcash(False)  # 允许卖空时使用保证金
    
    formatted_start = datetime.strptime(start_date, "%Y-%m-%d").strftime("%Y%m%d")
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    
    data_manager = FuturesDataManager(db_path=db_path)
    earliest_data = data_manager.query_data(
        symbol=symbol,
        start_date=None,  # 不限制开始日期
        end_date=None     # 不限制结束日期
    ).sort_values('date', ascending=False).tail(1)  # 按日期倒序取第一条
    print(f"earliest_data = {earliest_data}")
    need_update = False
    if earliest_data.empty:
        # 数据库中无该合约数据，需要更新
        need_update = True
    else:
        # 提取最早日期并转换为datetime对象
        earliest_data_str = earliest_data.iloc[0]['date']
        earliest_dt = datetime.strptime(earliest_data_str, "%Y-%m-%d")  # 假设date格式是YYYY-MM-DD
        # 若最早日期 < start_date，需要更新
        
        if start_dt < earliest_dt:
            need_update = True
    
    if need_update:
        logger.info(f"数据库中{symbol}的最新数据早于{start_date}，开始拉取更新...")
        contract_data = data_manager.fetch_main_contract_data(symbol, formatted_start)
        if not contract_data.empty:
            data_manager.save_to_database(contract_data)
            logger.info(f"{symbol}数据更新完成，新增/更新{len(contract_data)}条记录")
        else:
            logger.warning(f"未拉取到{symbol}的新数据")


    df = data_manager.query_data(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date
    )
    if df.empty:
        logger.error(f"未获取到{symbol}的历史数据")
        return None
    
    # 数据预处理
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    # df.set_index('date', inplace=True)
    
    print("数据列名：", df.columns.tolist())

    # 4. 添加数据到 cerebro
    data = FuturesDataFeed(dataname=df)
    cerebro.adddata(data, name=symbol)

    # 5. 添加策略
    cerebro.addstrategy(DualMaStrategy)

    # 6. 添加分析器（可选）
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name = 'trades')


    # 7. 运行回测
    logger.info(f"开始回测 {symbol}（{start_date} 至 {end_date}）")
    results = cerebro.run()
    strategy = results[0]
    
    # 8. 收集结果
    final_value = cerebro.broker.getvalue()
    sharpe_data = strategy.analyzers.sharpe.get_analysis()
    drawdown_data = strategy.analyzers.drawdown.get_analysis()
    returns_data = strategy.analyzers.returns.get_analysis()
    trades_data = strategy.analyzers.trades.get_analysis()
    
    result = {
        'symbol': symbol,
        'final_value': final_value,
        'total_return': returns_data.get('rtot', 0),
        'sharpe_ratio': sharpe_data.get('sharperatio', 0),
        'max_drawdown': drawdown_data['max']['drawdown'],
        'total_trades': trades_data.total.total if hasattr(trades_data.total, 'total') else 0,
        'winning_trades': trades_data.won.total if hasattr(trades_data.won, 'total') else 0,
        'losing_trades': trades_data.lost.total if hasattr(trades_data.lost, 'total') else 0,
    }
    
    if display:
        cerebro.plot(style='candlestick')
    
    return result




    # # 8. 输出结果
    # logger.info(f"最终资金: {cerebro.broker.getvalue():.2f} 元")
    # # 替换夏普比率输出代码
    # sharpe_data = strategy.analyzers.sharpe.get_analysis()
    # sharpe_ratio = sharpe_data.get('sharperatio')
    # if sharpe_ratio is not None:
    #     logger.info(f"夏普比率: {sharpe_ratio:.2f}")
    # else:
    #     logger.info("夏普比率: 无法计算（有效交易周期不足1年）")
    # logger.info(f"最大回撤: {strategy.analyzers.drawdown.get_analysis()['max']['drawdown']:.2f}%")
    # logger.info(f"总收益率: {strategy.analyzers.returns.get_analysis()['rtot']:.2%}")

    # 9. 绘制图表
    # cerebro.plot(style='candlestick')


