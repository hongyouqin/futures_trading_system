import backtrader as bt
import akshare as ak
import pandas as pd
import argparse
import numpy as np
import json
import os
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Set
from dataclasses import dataclass, asdict

from custom_indicators.rsiwithid import RSIWith_KD
from tool import send_markdown_to_dingding


@dataclass
class TradingSignal:
    """交易信号数据结构"""
    symbol: str
    name: str
    signal_type: str  # 'LONG' 或 'SHORT'
    signal_time: datetime
    current_price: float
    entry_price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    reason: str = ""
    confidence: float = 0.0
    k_value: float = 0.0
    d_value: float = 0.0
    volume: float = 0.0
    rsi: float = 0.0
    
    def to_markdown_text(self) -> str:
        """转换为Markdown格式文本"""
        emoji = "🟢" if self.signal_type == "LONG" else "🔴"
        direction = "做多" if self.signal_type == "LONG" else "做空"
        
        markdown = f"""## {emoji} 均值回归穿透监听

    ### 🏷️ 品种<font size=4>🎯 {self.symbol} {self.name} {direction} </font>**
    **🕐 时间**: {self.signal_time.strftime('%Y-%m-%d %H:%M:%S')}  
    **💰 当前价格**: {self.current_price:.2f}  
    **🎯 建议入场**: {self.entry_price:.2f}  

    ### 📋 信号概览
    **信号说明**: 均值回归用于无趋势时

    ### 📊 技术指标状态
    **K值**: {self.k_value:.1f}  
    **D值**: {self.d_value:.1f}"""
        
        if self.rsi > 0:
            markdown += f"\n**RSI**: {self.rsi:.1f}  "
            
        markdown += f"\n**信号信心**: {self.confidence:.1%}  "
        
        if self.volume > 0:
            markdown += f"\n**成交量**: {self.volume:.0f}  "
        
        if self.stop_loss:
            risk_percent = abs((self.stop_loss - self.entry_price) / self.entry_price * 100)
            markdown += f"""\n
    ### 🎯 风险控制
    **止损**: {self.stop_loss:.2f} ({risk_percent:.2f}%)"""
        
        if self.take_profit:
            profit_percent = abs((self.take_profit - self.entry_price) / self.entry_price * 100)
            markdown += f"""  
    **止盈**: {self.take_profit:.2f} ({profit_percent:.2f}%)"""
        
        markdown += f"""\n
    ### 📈 信号理由
    {self.reason}"""
        
        return markdown
    
    def get_signal_id(self) -> str:
        """获取信号唯一ID"""
        # 使用符号、类型、时间和KD值作为唯一ID
        time_str = self.signal_time.strftime('%Y%m%d_%H%M')
        k_str = f"{self.k_value:.1f}".replace('.', 'p')
        d_str = f"{self.d_value:.1f}".replace('.', 'p')
        return f"{self.symbol}_{self.signal_type}_{time_str}_K{k_str}_D{d_str}"
    
    def to_dict(self) -> dict:
        """转换为字典格式（可序列化）"""
        data = asdict(self)
        data['signal_time'] = self.signal_time.strftime('%Y-%m-%d %H:%M:%S')
        return data
    
    @classmethod
    def from_dict(cls, data: dict):
        """从字典创建信号对象"""
        data['signal_time'] = datetime.strptime(data['signal_time'], '%Y-%m-%d %H:%M:%S')
        return cls(**data)


class SignalHistoryManager:
    """信号历史管理器"""
    
    def __init__(self, history_file: str = "sent_signals.json"):
        self.history_file = history_file
        self.sent_signals: Dict[str, Dict] = self.load_history()
    
    def load_history(self) -> Dict[str, Dict]:
        """加载已发送信号历史"""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def save_history(self):
        """保存已发送信号历史"""
        with open(self.history_file, 'w', encoding='utf-8') as f:
            json.dump(self.sent_signals, f, ensure_ascii=False, indent=2)
    
    def is_signal_sent(self, signal: TradingSignal) -> bool:
        """检查信号是否已发送"""
        signal_id = signal.get_signal_id()
        return signal_id in self.sent_signals
    
    def mark_signal_as_sent(self, signal: TradingSignal):
        """标记信号为已发送"""
        signal_id = signal.get_signal_id()
        self.sent_signals[signal_id] = signal.to_dict()
        self.save_history()
    
    def get_all_sent_signals(self) -> List[TradingSignal]:
        """获取所有已发送信号"""
        signals = []
        for signal_data in self.sent_signals.values():
            try:
                signal = TradingSignal.from_dict(signal_data)
                signals.append(signal)
            except:
                continue
        return signals


class FuturesDataFeed(bt.feeds.PandasData):
    """适配期货数据的Backtrader数据源"""
    params = (
        ('datetime', 'datetime'),
        ('open', 'open'),
        ('high', 'high'),
        ('low', 'low'),
        ('close', 'close'),
        ('volume', 'volume'),
        ('openinterest', 'hold'),
    )


class PureKDScannerStrategy(bt.Strategy):
    """纯KD信号扫描策略"""
    
    params = (
        ('contracts', []),
        ('use_stop_loss', True),
        ('stop_loss_pct', 2.0),  # 止损百分比
        ('use_take_profit', True),
        ('take_profit_pct', 3.0),  # 止盈百分比
        ('oversold_level', 30),  # 超卖水平
        ('overbought_level', 70),  # 超买水平
        ('min_confidence', 0.5),  # 最小信号信心
        ('webhook_url', None),    # 钉钉Webhook URL
        ('min_bars', 30),        # 最少需要的数据条数
        ('symbol_name', None),
    )
    
    def __init__(self):
        self.indicators = {}
        self.kd_history = {}
        self.detected_signals: List[TradingSignal] = []  # 存储检测到的所有信号
        
        for i, data in enumerate(self.datas):
            symbol = data._name
            
            # 只使用RSIWith_KD指标
            self.indicators[symbol] = {
                'rsi_kd': RSIWith_KD(data),
            }
            
            self.kd_history[symbol] = {
                'k_values': [],
                'd_values': [],
                'timestamps': [],
            }
            
            print(f"初始化 {symbol} KD指标完成")
    
    def next(self):
        """扫描KD信号"""
        current_date = self.data.datetime.date(0)
        
        for i, data in enumerate(self.datas):
            symbol = data._name
            
            if len(data) < self.p.min_bars:
                continue
            
            # 检测信号
            signal = self._scan_for_kd_signal(symbol, data, current_date)
            
            if signal:
                self.detected_signals.append(signal)
                # print(f"📊 检测到信号: {symbol} {signal.signal_type} "
                #       f"(K:{signal.k_value:.1f}, D:{signal.d_value:.1f}, 信心:{signal.confidence:.1%})")
    
    def _scan_for_kd_signal(self, symbol: str, data, current_date) -> Optional[TradingSignal]:
        """扫描KD交易信号"""
        ind = self.indicators[symbol]
        current_time = data.datetime.datetime(0)
        
        # 获取KD值
        k_current = ind['rsi_kd'].k[0]
        d_current = ind['rsi_kd'].d[0]
        
        # 保存历史值
        self.kd_history[symbol]['k_values'].append(k_current)
        self.kd_history[symbol]['d_values'].append(d_current)
        self.kd_history[symbol]['timestamps'].append(current_time)
        
        # 只保留最近50个值
        if len(self.kd_history[symbol]['k_values']) > 50:
            self.kd_history[symbol]['k_values'] = self.kd_history[symbol]['k_values'][-50:]
            self.kd_history[symbol]['d_values'] = self.kd_history[symbol]['d_values'][-50:]
            self.kd_history[symbol]['timestamps'] = self.kd_history[symbol]['timestamps'][-50:]
        
        if len(self.kd_history[symbol]['k_values']) < 5:
            return None
        
        # 获取KD历史数据
        k_values = self.kd_history[symbol]['k_values']
        d_values = self.kd_history[symbol]['d_values']
        
        # 当前值
        k_current = k_values[-1]
        k_prev = k_values[-2] if len(k_values) >= 2 else k_current
        d_current = d_values[-1]
        d_prev = d_values[-2] if len(d_values) >= 2 else d_current
        
        # 检查KD交叉
        golden_cross = k_prev <= d_prev and k_current > d_current
        death_cross = k_prev >= d_prev and k_current < d_current
        
        signal = None
        
        # 做多信号检测：金叉 + 从超卖区回升
        if golden_cross:
            # 检查是否从超卖区开始
            if self._is_coming_from_oversold(k_values, d_values):
                signal = self._create_kd_long_signal(symbol, data, current_time, 
                                                   k_prev, d_prev, k_current, d_current)
        
        # 做空信号检测：死叉 + 从超买区回落
        elif death_cross:
            # 检查是否从超买区开始
            if self._is_coming_from_overbought(k_values, d_values):
                signal = self._create_kd_short_signal(symbol, data, current_time,
                                                    k_prev, d_prev, k_current, d_current)
        
        return signal
    
    def _is_coming_from_oversold(self, k_values: List[float], d_values: List[float]) -> bool:
        """检查是否从超卖区开始回升"""
        if len(k_values) < 3:
            return False
        
        lookback = min(3, len(k_values) - 1)
        oversold_count = 0
        
        for i in range(1, lookback + 1):
            idx = -1 - i
            if idx < -len(k_values):
                break
                
            k_val = k_values[idx]
            d_val = d_values[idx]
            
            if k_val < self.p.oversold_level or d_val < self.p.oversold_level:
                oversold_count += 1
        
        return oversold_count >= 1
    
    def _is_coming_from_overbought(self, k_values: List[float], d_values: List[float]) -> bool:
        """检查是否从超买区开始回落"""
        if len(k_values) < 3:
            return False
        
        lookback = min(3, len(k_values) - 1)
        overbought_count = 0
        
        for i in range(1, lookback + 1):
            idx = -1 - i
            if idx < -len(k_values):
                break
                
            k_val = k_values[idx]
            d_val = d_values[idx]
            
            if k_val > self.p.overbought_level or d_val > self.p.overbought_level:
                overbought_count += 1
        
        return overbought_count >= 1
    
    def _create_kd_long_signal(self, symbol: str, data, current_time, 
                              k_prev, d_prev, k_current, d_current) -> Optional[TradingSignal]:
        """创建KD金叉做多信号"""
        current_price = data.close[0]
        volume = data.volume[0]
        
        # 获取RSI值（如果可用）
        rsi = 0
        try:
            ind = self.indicators[symbol]
            if hasattr(ind['rsi_kd'], 'rsi'):
                rsi = ind['rsi_kd'].rsi[0]
        except:
            pass
        
        # 计算止损止盈
        if self.p.use_stop_loss:
            stop_loss = current_price * (1 - self.p.stop_loss_pct / 100)
        else:
            stop_loss = None
            
        if self.p.use_take_profit:
            take_profit = current_price * (1 + self.p.take_profit_pct / 100)
        else:
            take_profit = None
        
        # 计算信号信心度
        confidence = self._calculate_kd_confidence(
            k_current, d_current, 'LONG'
        )
        
        if confidence < self.p.min_confidence:
            return None
        
        # 创建信号理由
        reason_lines = []
        reason_lines.append(f"KD金叉信号 (K:{k_prev:.1f}→{k_current:.1f}, D:{d_prev:.1f}→{d_current:.1f})")
        
        if k_current < 20:
            reason_lines.append("K值极低，超卖严重")
        elif k_current < 30:
            reason_lines.append("K值在超卖区")
        
        if k_current > d_current:
            diff_percent = abs(k_current - d_current) / d_current * 100
            reason_lines.append(f"K值高于D值{diff_percent:.1f}%")
        
        reason = " | ".join(reason_lines)
        
        return TradingSignal(
            symbol=symbol,
            name = self.p.symbol_name,
            signal_type='LONG',
            signal_time=current_time,
            current_price=current_price,
            entry_price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            reason=reason,
            confidence=confidence,
            k_value=k_current,
            d_value=d_current,
            volume=volume,
            rsi=rsi
        )
    
    def _create_kd_short_signal(self, symbol: str, data, current_time,
                               k_prev, d_prev, k_current, d_current) -> Optional[TradingSignal]:
        """创建KD死叉做空信号"""
        current_price = data.close[0]
        volume = data.volume[0]
        
        # 获取RSI值（如果可用）
        rsi = 0
        try:
            ind = self.indicators[symbol]
            if hasattr(ind['rsi_kd'], 'rsi'):
                rsi = ind['rsi_kd'].rsi[0]
        except:
            pass
        
        # 计算止损止盈
        if self.p.use_stop_loss:
            stop_loss = current_price * (1 + self.p.stop_loss_pct / 100)
        else:
            stop_loss = None
            
        if self.p.use_take_profit:
            take_profit = current_price * (1 - self.p.take_profit_pct / 100)
        else:
            take_profit = None
        
        # 计算信号信心度
        confidence = self._calculate_kd_confidence(
            k_current, d_current, 'SHORT'
        )
        
        if confidence < self.p.min_confidence:
            return None
        
        # 创建信号理由
        reason_lines = []
        reason_lines.append(f"KD死叉信号 (K:{k_prev:.1f}→{k_current:.1f}, D:{d_prev:.1f}→{d_current:.1f})")
        
        if k_current > 80:
            reason_lines.append("K值极高，超买严重")
        elif k_current > 70:
            reason_lines.append("K值在超买区")
        
        if k_current < d_current:
            diff_percent = abs(d_current - k_current) / k_current * 100
            reason_lines.append(f"K值低于D值{diff_percent:.1f}%")
        
        reason = " | ".join(reason_lines)
        
        return TradingSignal(
            symbol=symbol,
            name = self.p.symbol_name,
            signal_type='SHORT',
            signal_time=current_time,
            current_price=current_price,
            entry_price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            reason=reason,
            confidence=confidence,
            k_value=k_current,
            d_value=d_current,
            volume=volume,
            rsi=rsi
        )
    
    def _calculate_kd_confidence(self, k_value: float, d_value: float, signal_type: str) -> float:
        """计算KD信号的信心度"""
        confidence = 0.3  # 基础信心
        
        if signal_type == 'LONG':
            if k_value < 20 and d_value < 20:
                confidence += 0.4
            elif k_value < 30 and d_value < 30:
                confidence += 0.3
            elif k_value < 40:
                confidence += 0.1
                
            if k_value > d_value:
                confidence += 0.1
                
        else:  # SHORT
            if k_value > 80 and d_value > 80:
                confidence += 0.4
            elif k_value > 70 and d_value > 70:
                confidence += 0.3
            elif k_value > 60:
                confidence += 0.1
                
            if k_value < d_value:
                confidence += 0.1
        
        kd_diff = abs(k_value - d_value)
        if kd_diff > 10:
            confidence += 0.1
        elif kd_diff > 5:
            confidence += 0.05
        
        return min(max(confidence, 0), 1)
    
    def stop(self):
        """策略结束"""
        print("\n" + "="*60)
        print("KD信号扫描完成")
        print("="*60)
        
        if self.detected_signals:
            print(f"\n📊 总共检测到 {len(self.detected_signals)} 个信号")
        else:
            print("\n⚠️ 未检测到任何KD信号")


def process_and_send_latest_signal(strategy, webhook_url: str, history_file: str = "sent_signals.json"):
    """处理并发送最新的信号"""
    if not strategy.detected_signals:
        print("\n⚠️ 没有检测到任何信号，无需处理")
        return None
    
    # 1. 按时间排序，获取最新信号
    latest_signals = sorted(strategy.detected_signals, key=lambda x: x.signal_time, reverse=True)
    latest_signal = latest_signals[0]
    
    print(f"\n🔍 找到最新信号:")
    print(f"  标的: {latest_signal.symbol}")
    print(f"  类型: {latest_signal.signal_type}")
    print(f"  时间: {latest_signal.signal_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  价格: {latest_signal.current_price:.2f}")
    print(f"  K/D: {latest_signal.k_value:.1f}/{latest_signal.d_value:.1f}")
    print(f"  信心: {latest_signal.confidence:.1%}")
    
    # 2. 加载历史记录
    history_manager = SignalHistoryManager(history_file)
    
    # 3. 检查是否已发送过
    if history_manager.is_signal_sent(latest_signal):
        print(f"\n⏭️ 信号已发送过，跳过")
        print(f"  信号ID: {latest_signal.get_signal_id()}")
        return None
    
    # 4. 发送信号
    if webhook_url:
        print(f"\n🚀 发送最新信号到钉钉...")
        try:
            # 获取Markdown内容
            markdown_text = latest_signal.to_markdown_text()
            
            # 打印要发送的内容
            print(f"\n📝 发送内容预览:")
            print("-"*40)
            print(markdown_text)
            print("-"*40)
            
            # 发送到钉钉
            send_markdown_to_dingding(msg=markdown_text)
            print(f"✅ 成功发送信号到钉钉")
            
            # 5. 记录到历史
            history_manager.mark_signal_as_sent(latest_signal)
            print(f"📝 已记录到历史文件: {history_file}")
            
            return latest_signal
            
        except Exception as e:
            print(f"❌ 发送失败: {e}")
            return None
    else:
        print(f"\nℹ️ 未配置钉钉Webhook，不发送信号")
        return None


# 主函数
def kd_scanner(data_df: pd.DataFrame, symbol: str, symbol_name: str=None, webhook_url: str = None, history_file: str = "sent_signals.json") -> dict:
    """
    KD信号扫描器
    Args:
        data_df: K线数据DataFrame，需要包含datetime, open, high, low, close, volume等列
        symbol: 合约代码
        webhook_url: 钉钉Webhook URL（可选）
        history_file: 历史记录文件路径
    Returns:
        dict: 扫描结果
    """
    cerebro = bt.Cerebro()
    
    # 使用纯KD信号扫描策略
    cerebro.addstrategy(
        PureKDScannerStrategy,
        contracts=[symbol],
        min_confidence=0.5,
        oversold_level=30,
        overbought_level=70,
        symbol_name = symbol_name
    )
    
    # 检查数据格式
    if 'datetime' not in data_df.columns:
        print("❌ 数据必须包含'datetime'列")
        return {"success": False, "error": "数据格式错误"}
    
    # 确保数据已排序
    data_df = data_df.sort_values('datetime').copy()
    
    # 检查历史文件
    if os.path.exists(history_file):
        history_manager = SignalHistoryManager(history_file)
        sent_count = len(history_manager.sent_signals)
        print(f"📚 历史记录: {sent_count} 个已发送信号")
    else:
        print("📚 历史记录: 新文件，无历史记录")
    
    # 添加数据
    try:
        data = FuturesDataFeed(dataname=data_df)
        data._name = symbol        
        cerebro.adddata(data)
        
        print(f"✓ 已加载数据: {symbol} ({len(data_df)}条K线)")
        print(f"  数据时间范围: {data_df['datetime'].iloc[0]} ~ {data_df['datetime'].iloc[-1]}")
        
    except Exception as e:
        print(f"❌ 数据加载失败: {e}")
        return {"success": False, "error": f"数据加载失败: {e}"}
    
    print(f"\n🚀 开始扫描KD信号...")
    print("-"*60)
    
    # 运行扫描
    try:
        cerebro.run()
    except Exception as e:
        print(f"❌ 扫描运行失败: {e}")
        return {"success": False, "error": f"扫描运行失败: {e}"}
    
    # 获取策略实例
    if cerebro.runstrats and len(cerebro.runstrats) > 0:
        strategy = cerebro.runstrats[0][0]
        
        print(f"\n📊 扫描完成:")
        print(f"  检测到信号总数: {len(strategy.detected_signals)} 个")
        
        if strategy.detected_signals:
            # 显示最近几个信号
            recent_signals = sorted(strategy.detected_signals, key=lambda x: x.signal_time, reverse=True)[:3]
            print(f"\n🔍 最近信号:")
            for i, sig in enumerate(recent_signals, 1):
                emoji = "🟢" if sig.signal_type == "LONG" else "🔴"
                print(f"{i}. {emoji} {sig.signal_time.strftime('%H:%M')} {sig.signal_type} "
                      f"(K:{sig.k_value:.1f}, D:{sig.d_value:.1f}, 信心:{sig.confidence:.1%})")
        
        # 处理并发送最新信号
        sent_signal = process_and_send_latest_signal(strategy, webhook_url, history_file)
        
        result = {
            "success": True,
            "symbol": symbol,
            "total_signals": len(strategy.detected_signals),
            "sent_new_signal": sent_signal is not None,
        }
        
        if sent_signal:
            result["sent_signal"] = {
                "signal_id": sent_signal.get_signal_id(),
                "signal_type": sent_signal.signal_type,
                "signal_time": sent_signal.signal_time.strftime('%Y-%m-%d %H:%M:%S'),
                "price": sent_signal.current_price,
                "k_value": sent_signal.k_value,
                "d_value": sent_signal.d_value,
                "confidence": sent_signal.confidence,
            }
            print(f"\n🎉 成功发送最新信号!")
        else:
            print(f"\nℹ️ 本次运行未发送任何新信号")
        
        return result
    else:
        print("❌ 策略运行失败")
        return {"success": False, "error": "策略运行失败"}
        

def main():
    parser = argparse.ArgumentParser(description='KD均值回归信号扫描系统')
    parser.add_argument('--symbols', nargs='+', required=True, help='合约代码列表')
    parser.add_argument('--period', default='15min', help='K线周期 (1min, 5min, 15min, 30min, 60min)')
    parser.add_argument('--start_date', default=None, help='开始日期 (YYYY-MM-DD)')
    parser.add_argument('--end_date', default=None, help='结束日期 (YYYY-MM-DD)')
    parser.add_argument('--webhook', default=None, help='钉钉Webhook URL')
    parser.add_argument('--min_confidence', type=float, default=0.5, help='最小信号信心度 (0-1)')
    parser.add_argument('--oversold', type=int, default=30, help='超卖水平')
    parser.add_argument('--overbought', type=int, default=70, help='超买水平')
    parser.add_argument('--stop_loss', type=float, default=2.0, help='止损百分比')
    parser.add_argument('--take_profit', type=float, default=3.0, help='止盈百分比')
    parser.add_argument('--history_file', default='sent_signals.json', help='历史记录文件')
    
    args = parser.parse_args()
    
    cerebro = bt.Cerebro()
    
    # 使用纯KD信号扫描策略
    cerebro.addstrategy(
        PureKDScannerStrategy,
        contracts=args.symbols,
        webhook_url=args.webhook,
        min_confidence=args.min_confidence,
        oversold_level=args.oversold,
        overbought_level=args.overbought,
        stop_loss_pct=args.stop_loss,
        take_profit_pct=args.take_profit,
    )
    
    print("\n" + "="*60)
    print("KD均值回归信号扫描系统启动")
    print("每次运行只发送最新的一条未发送信号")
    print("="*60)
    
    # 检查历史文件
    if os.path.exists(args.history_file):
        history_manager = SignalHistoryManager(args.history_file)
        sent_count = len(history_manager.sent_signals)
        print(f"📚 历史记录: {sent_count} 个已发送信号")
    else:
        print("📚 历史记录: 新文件，无历史记录")
    
    # 添加数据
    data_count = 0
    loaded_symbols = []
    for symbol in args.symbols:
        try:
            print(f"\n正在加载 {symbol} 数据...")
            data_df = ak.futures_zh_minute_sina(symbol=symbol, period=args.period)
            
            if data_df.empty:
                print(f"⚠️  {symbol} 数据为空")
                continue
                
            data_df['datetime'] = pd.to_datetime(data_df['datetime'])
            data_df = data_df.sort_values('datetime')
            
            # 如果有日期范围，进行筛选
            if args.start_date:
                start_dt = pd.to_datetime(args.start_date)
                data_df = data_df[data_df['datetime'] >= start_dt]
            
            if args.end_date:
                end_dt = pd.to_datetime(args.end_date)
                data_df = data_df[data_df['datetime'] <= end_dt]
            
            if len(data_df) < 100:
                print(f"⚠️  {symbol} 数据不足({len(data_df)}条)，跳过")
                continue
            
            data = FuturesDataFeed(dataname=data_df)
            data._name = symbol
            
            cerebro.adddata(data)
            data_count += 1
            loaded_symbols.append(symbol)
            print(f"✓ 已加载: {symbol} ({len(data_df)}条{args.period}数据)")
            
        except Exception as e:
            print(f"✗ 加载失败 {symbol}: {e}")
    
    if data_count == 0:
        print("❌ 错误: 没有成功加载任何数据")
        return
    
    print(f"\n📋 扫描参数:")
    print(f"  成功加载标的: {data_count}个")
    print(f"  标的列表: {', '.join(loaded_symbols)}")
    print(f"  K线周期: {args.period}")
    print(f"  超卖水平: K/D < {args.oversold}")
    print(f"  超买水平: K/D > {args.overbought}")
    print(f"  止损: {args.stop_loss}%")
    print(f"  止盈: {args.take_profit}%")
    print(f"  最小信心度: {args.min_confidence}")
    print(f"  历史文件: {args.history_file}")
    
    if args.webhook:
        print(f"  钉钉通知: 已启用")
    else:
        print(f"  钉钉通知: 未启用（仅记录到文件）")
    
    print(f"\n🚀 开始扫描KD信号...")
    print("-"*60)
    
    # 运行扫描
    cerebro.run()
    
    # 获取策略实例
    if cerebro.runstrats and len(cerebro.runstrats) > 0:
        strategy = cerebro.runstrats[0][0]
        
        # 处理并发送最新信号
        sent_signal = process_and_send_latest_signal(strategy, args.webhook, args.history_file)
        
        if sent_signal:
            print(f"\n🎉 成功发送最新信号!")
            print(f"  信号ID: {sent_signal.get_signal_id()}")
        else:
            print(f"\nℹ️ 本次运行未发送任何新信号")
        
        # 显示历史统计
        history_manager = SignalHistoryManager(args.history_file)
        sent_count = len(history_manager.sent_signals)
        print(f"\n📊 历史统计:")
        print(f"  总已发送信号: {sent_count} 个")
        
        if sent_count > 0:
            sent_signals = history_manager.get_all_sent_signals()
            sent_signals.sort(key=lambda x: x.signal_time, reverse=True)
            
            print(f"\n📅 最近5条已发送信号:")
            print("-"*60)
            for i, sig in enumerate(sent_signals[:5], 1):
                emoji = "🟢" if sig.signal_type == "LONG" else "🔴"
                print(f"{i}. {emoji} {sig.signal_time.strftime('%m-%d %H:%M')} {sig.symbol} {sig.signal_type}")
                print(f"   价格: {sig.current_price:.2f} | K/D: {sig.k_value:.1f}/{sig.d_value:.1f}")
                print("-"*60)
        
        print(f"\n✅ 扫描处理完成!")
    else:
        print("❌ 策略运行失败")


if __name__ == '__main__':
    main()