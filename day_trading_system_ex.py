import argparse
import logging
from logging.handlers import TimedRotatingFileHandler
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import sys
from dotenv import load_dotenv
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import threading
import time as ttime

import pandas as pd
import schedule
import time
import json
import os

from my_backtrader.day_trading_signal_generator_plus import run_strategy_with_three_timeframes
from tool import send_to_dingding

# 信号记录文件路径
SIGNAL_HISTORY_FILE = 'signal_history_plus.json'
ACTIVE_SIGNALS_FILE = 'active_signals.json'
SYMBOLS_CONFIG_FILE = 'symbols_config.xlsx'

symbol_to_name_dict = None

@dataclass
class DonchianSignal:
    """唐奇安通道突破信号"""
    symbol: str
    symbol_name: str
    signal_type: str  # 'LONG' or 'SHORT'
    entry_price: float
    donchian_high: float
    donchian_low: float
    current_price: float
    timestamp: datetime
    original_signal_id: str  # 原始三重滤网信号ID
    status: str = 'PENDING'  # PENDING, TRIGGERED, EXPIRED
    triggered_time: Optional[datetime] = None
    trigger_price: Optional[float] = None

class DonchianBreakoutMonitor:
    """唐奇安通道突破监控器"""
    
    def __init__(self, period=20):
        """
        初始化监控器
        Args:
            period: 唐奇安通道周期
        """
        self.period = period
        self.active_signals: Dict[str, List[DonchianSignal]] = {}
        self.load_active_signals()
        
    def load_active_signals(self):
        """加载活跃信号"""
        if os.path.exists(ACTIVE_SIGNALS_FILE):
            with open(ACTIVE_SIGNALS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for symbol, signals in data.items():
                    self.active_signals[symbol] = []
                    for signal_data in signals:
                        signal = DonchianSignal(
                            symbol=signal_data['symbol'],
                            symbol_name=signal_data['symbol_name'],
                            signal_type=signal_data['signal_type'],
                            entry_price=signal_data['entry_price'],
                            donchian_high=signal_data['donchian_high'],
                            donchian_low=signal_data['donchian_low'],
                            current_price=signal_data['current_price'],
                            timestamp=datetime.fromisoformat(signal_data['timestamp']),
                            original_signal_id=signal_data['original_signal_id'],
                            status=signal_data['status'],
                            triggered_time=datetime.fromisoformat(signal_data['triggered_time']) if signal_data['triggered_time'] else None,
                            trigger_price=signal_data['trigger_price']
                        )
                        self.active_signals[symbol].append(signal)
    
    def save_active_signals(self):
        """保存活跃信号"""
        data = {}
        for symbol, signals in self.active_signals.items():
            data[symbol] = []
            for signal in signals:
                signal_data = {
                    'symbol': signal.symbol,
                    'symbol_name': signal.symbol_name,
                    'signal_type': signal.signal_type,
                    'entry_price': signal.entry_price,
                    'donchian_high': signal.donchian_high,
                    'donchian_low': signal.donchian_low,
                    'current_price': signal.current_price,
                    'timestamp': signal.timestamp.isoformat(),
                    'original_signal_id': signal.original_signal_id,
                    'status': signal.status,
                    'triggered_time': signal.triggered_time.isoformat() if signal.triggered_time else None,
                    'trigger_price': signal.trigger_price
                }
                data[symbol].append(signal_data)
        
        with open(ACTIVE_SIGNALS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def calculate_donchian_channels(self, price_data: List[float]) -> Tuple[float, float]:
        """
        计算唐奇安通道
        Args:
            price_data: 价格数据列表（最新数据在最后）
        Returns:
            (最高价, 最低价)
        """
        if len(price_data) < self.period:
            return max(price_data), min(price_data)
        
        recent_prices = price_data[-self.period:]
        return max(recent_prices), min(recent_prices)
    
    def register_signal(self, triple_filter_signal: dict, symbol: str, symbol_name: str = None):
        """
        注册新的三重滤网信号进行监控
        Args:
            triple_filter_signal: 三重滤网信号
            symbol: 品种代码
            symbol_name: 品种名称
        """
        # 只处理LONG和SHORT信号
        if triple_filter_signal['signal_type'] not in ['LONG', 'SHORT']:
            return
        
        # 获取1分钟数据计算唐奇安通道
        try:
            import akshare as ak
            df_1min = ak.futures_zh_minute_sina(symbol=symbol, period=1)
            
            if df_1min.empty or len(df_1min) < self.period:
                logging.warning(f"⚠️  {symbol} 1分钟数据不足，无法计算唐奇安通道")
                return
            
            # 计算唐奇安通道
            highs = df_1min['high'].tolist()
            lows = df_1min['low'].tolist()
            
            donchian_high, donchian_low = self.calculate_donchian_channels(highs)
            current_price = df_1min['close'].iloc[-1]
            
            # 创建唐奇安信号
            signal = DonchianSignal(
                symbol=symbol,
                symbol_name=symbol_name or symbol,
                signal_type=triple_filter_signal['signal_type'],
                entry_price=triple_filter_signal['price'],
                donchian_high=donchian_high,
                donchian_low=donchian_low,
                current_price=current_price,
                timestamp=datetime.now(),
                original_signal_id=triple_filter_signal.get('signal_id', 'unknown')
            )
            
            # 添加到活跃信号
            if symbol not in self.active_signals:
                self.active_signals[symbol] = []
            
            self.active_signals[symbol].append(signal)
            self.save_active_signals()
            
            logging.info(f"✅ 已注册唐奇安监控信号: {symbol} {signal.signal_type}")
            logging.info(f"   唐奇安通道: 高={donchian_high:.2f}, 低={donchian_low:.2f}")
            logging.info(f"   当前价格: {current_price:.2f}")
            
        except Exception as e:
            logging.error(f"❌ 注册唐奇安信号失败 {symbol}: {e}")
    
    def check_breakout(self, symbol: str) -> List[DonchianSignal]:
        """
        检查指定品种的突破信号
        Args:
            symbol: 品种代码
        Returns:
            触发突破的信号列表
        """
        if symbol not in self.active_signals:
            return []
        
        triggered_signals = []
        
        try:
            import akshare as ak
            df_1min = ak.futures_zh_minute_sina(symbol=symbol, period=1)
            
            if df_1min.empty:
                return triggered_signals
            
            current_price = df_1min['close'].iloc[-1]
            current_time = datetime.now()
            
            for signal in self.active_signals[symbol][:]:  # 使用副本遍历
                # 检查信号是否过期（1小时）
                if current_time - signal.timestamp > timedelta(hours=1):
                    signal.status = 'EXPIRED'
                    logging.info(f"⏰ 信号过期: {symbol} {signal.signal_type}")
                    continue
                
                # 检查突破
                if signal.signal_type == 'LONG':
                    # 多头信号：价格突破唐奇安通道上轨
                    if current_price > signal.donchian_high:
                        signal.status = 'TRIGGERED'
                        signal.triggered_time = current_time
                        signal.trigger_price = current_price
                        triggered_signals.append(signal)
                        logging.info(f"🎯 多头突破触发: {symbol} 价格={current_price:.2f} > 通道上轨={signal.donchian_high:.2f}")
                
                elif signal.signal_type == 'SHORT':
                    # 空头信号：价格突破唐奇安通道下轨
                    if current_price < signal.donchian_low:
                        signal.status = 'TRIGGERED'
                        signal.triggered_time = current_time
                        signal.trigger_price = current_price
                        triggered_signals.append(signal)
                        logging.info(f"🎯 空头突破触发: {symbol} 价格={current_price:.2f} < 通道下轨={signal.donchian_low:.2f}")
            
            # 移除已触发或过期的信号
            self.active_signals[symbol] = [
                s for s in self.active_signals[symbol] 
                if s.status == 'PENDING'
            ]
            
            # 如果该品种没有活跃信号，从字典中移除
            if not self.active_signals[symbol]:
                del self.active_signals[symbol]
            
            self.save_active_signals()
            
        except Exception as e:
            logging.error(f"❌ 检查突破失败 {symbol}: {e}")
        
        return triggered_signals
    
    def monitor_all_active_signals(self):
        """监控所有活跃信号"""
        logging.info("🔍 开始检查所有活跃信号的唐奇安突破...")
        
        symbols_to_check = list(self.active_signals.keys())
        total_triggered = 0
        
        for symbol in symbols_to_check:
            triggered = self.check_breakout(symbol)
            if triggered:
                total_triggered += len(triggered)
                for signal in triggered:
                    self.send_breakout_notification(signal)
            
            # 避免请求过于频繁
            ttime.sleep(1)
        
        if total_triggered > 0:
            logging.info(f"🎯 本次监控发现 {total_triggered} 个突破信号")
        else:
            logging.info("📭 本次监控未发现突破信号")
    
    def send_breakout_notification(self, signal: DonchianSignal):
        """发送突破通知"""
        try:
            # 这里可以集成你的邮件或钉钉通知
            subject = f"唐奇安通道突破 - {signal.symbol} {signal.signal_type}"
            message = f"""
🚨 唐奇安通道突破触发 🚨

品种: {signal.symbol_name}
品种代码: {signal.symbol}
信号类型: {signal.signal_type}
触发时间: {signal.triggered_time}
触发价格: {signal.trigger_price:.2f}
唐奇安通道: 上轨={signal.donchian_high:.2f}, 下轨={signal.donchian_low:.2f}
原始信号ID: {signal.original_signal_id}

💡 操作建议:
{'考虑进场做多' if signal.signal_type == 'LONG' else '考虑进场做空'}

⚠️ 风险提示: 投资有风险，入市需谨慎
"""
            logging.info(f"📤 突破通知: {subject}")
            logging.info(message)
            
            # 可以在这里调用你的通知函数
            send_to_dingding(message=message)
            
        except Exception as e:
            logging.error(f"❌ 发送突破通知失败: {e}")
    
    def get_active_signal_count(self) -> int:
        """获取活跃信号数量"""
        total = 0
        for signals in self.active_signals.values():
            total += len([s for s in signals if s.status == 'PENDING'])
        return total
    
    def cleanup_expired_signals(self):
        """清理过期信号"""
        current_time = datetime.now()
        expired_count = 0
        
        for symbol in list(self.active_signals.keys()):
            original_count = len(self.active_signals[symbol])
            self.active_signals[symbol] = [
                s for s in self.active_signals[symbol]
                if current_time - s.timestamp <= timedelta(hours=1)
            ]
            expired_count += original_count - len(self.active_signals[symbol])
            
            # 如果该品种没有活跃信号，从字典中移除
            if not self.active_signals[symbol]:
                del self.active_signals[symbol]
        
        if expired_count > 0:
            logging.info(f"🗑️  已清理 {expired_count} 个过期信号")
            self.save_active_signals()

# 全局唐奇安监控器实例
donchian_monitor = DonchianBreakoutMonitor(period=20)

def load_symbols_from_excel(config_file):
    """从Excel文件加载品种配置"""
    try:
        if not os.path.exists(config_file):
            logging.error(f"❌ 品种配置文件 {config_file} 不存在")
            return []
        
        df = pd.read_excel(config_file)
        
        # 检查必要的列是否存在
        if 'symbol' not in df.columns:
            logging.error("❌ Excel文件中缺少 'symbol' 列")
            return []
        
        # 转换成字典
        global symbol_to_name_dict
        df_copy = df.copy()
        symbol_to_name_dict = df_copy.set_index('symbol')['name'].to_dict()
        
        # 返回symbol列表
        symbols = df['symbol'].dropna().tolist()
        logging.info(f"✅ 从Excel加载了 {len(symbols)} 个品种")
        return symbols
        
    except Exception as e:
        logging.error(f"❌ 读取品种配置文件失败: {e}")
        return []

def parse_args():
    '''
    参数解析
    '''
    parser = argparse.ArgumentParser(  
        description='日内交易系统')
    parser.add_argument('--symbol', default="", 
                        help="期货商品编号，多个品种用逗号分隔")
    parser.add_argument('--symbol_config_file', default="symbols_config.xlsx", 
                        help="期货商品配置文件，默认是全部，夜盘建议用overnight_symbols_config.xlsx")
    parser.add_argument('--file', action='store_true',
                        help="从Excel文件读取品种列表")
    parser.add_argument('--gso', choices=['true', 'false', 'True', 'False', '1', '0'], 
                        default='true', help="是否只产生信号")
    parser.add_argument('--exec', choices=['test', 'schedule'], required=True, 
                        help="执行模式：test(单个商品测试) 或 schedule(定时执行)")
    parser.add_argument('--email', help="接收通知的邮箱地址")
    parser.add_argument('--interval', type=int, default=3, 
                        help="定时执行间隔(分钟)")
    parser.add_argument('--donchian_period', type=int, default=20,
                        help="唐奇安通道周期")
    return parser.parse_args()

def load_signal_history():
    """加载历史信号记录"""
    if os.path.exists(SIGNAL_HISTORY_FILE):
        with open(SIGNAL_HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_signal_history(history):
    """保存信号记录"""
    with open(SIGNAL_HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def send_email_notification(symbol, signal_info, receiver_email):
    """发送邮件通知"""
    time.sleep(random.uniform(1, 2))
    try:
        # 邮件配置
        smtp_server = os.getenv("SMTP_SERVER")
        port = os.getenv("PORT")
        sender_email = os.getenv("SENDER_EMAIL")
        password = os.getenv("PWD")
        
        # 创建邮件内容
        message = MIMEMultipart()
        message["Subject"] = f"期货合约信号 - {symbol} - {signal_info['signal_type']}"
        message["From"] = sender_email
        message["To"] = receiver_email

        # 邮件正文
        signal_time = signal_info['timestamp']
        if isinstance(signal_time, str):
            signal_time = signal_info['timestamp']
        else:
            signal_time = signal_info['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
        
        symbol_name = None
        if symbol_to_name_dict is not None:
            symbol_name = symbol_to_name_dict.get(symbol)
            
        body = f"""
🚀 新的交易信号 🚀

品种: {symbol_name}
品种代码: {symbol}
时间: {signal_time}
信号类型: {signal_info['signal_type']}
{'考虑做多' if signal_info['signal_type'] == 'LONG' else '考虑做空' if signal_info['signal_type'] == 'SHORT' else '保持观望'}

价格: {signal_info['price']:.2f}
趋势: {'上涨' if signal_info['trend'] == 1 else '下跌' if signal_info['trend'] == -1 else '震荡'}
力度指数: {signal_info['force_index']:.2f}
EMA快线: {signal_info['ema_fast']:.2f}
EMA慢线: {signal_info['ema_slow']:.2f}
价值上通道: {signal_info['value_up_channel']}
价值下通道：{signal_info['value_down_channel']}
价值通道大小：{signal_info['value_size']}
做多入场价：{signal_info['suggested_buy_long']}
做多与当前价的距离：{signal_info['distance_to_buy']}
做空入场价：{signal_info['suggested_sell_short']}
做空与当前价的距离: {signal_info['distance_to_sell']}
市场强度: {signal_info['market_strength']}
市场强度分数：{signal_info['market_strength_score']}
ATR: {signal_info['atr']}

⚠️ 风险提示: 投资有风险，入市需谨慎
"""
        
        message.attach(MIMEText(body, "plain", "utf-8"))

        # 使用SMTP_SSL连接（关键修改）
        server = smtplib.SMTP_SSL(smtp_server, port)
        server.login(sender_email, password)
        server.sendmail(sender_email, receiver_email, message.as_string())
        server.quit()
        
        logging.info(f"📧 邮件通知已发送至: {receiver_email}")
        return True
        
    except Exception as e:
        logging.error(f"❌ 邮件发送失败: {e}")
        return False

def check_new_signals(symbol, current_signals, receiver_email=None):
    """检查新信号并发送通知（优化版：收集所有新信号，只发最新一条）"""
    history = load_signal_history()
    
    # 首次检测该品种
    is_first = False
    if symbol not in history:
        logging.info(f"首次检测到品种 {symbol}，跳过邮件通知")
        history[symbol] = []
        is_first = True
    
    # 收集所有新信号
    new_signals = []
    
    # 获取该品种最新的信号时间
    latest_signal_time = None
    if history[symbol]:
        # 从历史记录中提取所有时间戳并找到最新的
        timestamps = []
        for signal_id in history[symbol]:
            try:
                # 解析信号ID获取时间戳部分
                parts = signal_id.split('_')
                if len(parts) >= 3:
                    time_str = parts[1]  # 时间戳部分
                    # 尝试解析时间戳
                    if 'T' in time_str:  # ISO格式
                        signal_time = datetime.fromisoformat(time_str)
                    else:  # 字符串格式
                        signal_time = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
                    timestamps.append(signal_time)
            except (ValueError, IndexError) as e:
                logging.warning(f"警告: 解析历史信号时间失败 {signal_id}: {e}")
                continue
        
        if timestamps:
            latest_signal_time = max(timestamps)
            logging.info(f"历史最新信号时间: {latest_signal_time}")
    
    for signal in current_signals:
        # 确保信号时间戳是datetime对象
        signal_time = signal['timestamp']
        if isinstance(signal_time, str):
            try:
                if 'T' in signal_time:  # ISO格式
                    signal_time = datetime.fromisoformat(signal_time)
                else:  # 字符串格式
                    signal_time = datetime.strptime(signal_time, '%Y-%m-%d %H:%M:%S')
            except ValueError as e:
                logging.warning(f"警告: 解析当前信号时间失败 {signal_time}: {e}")
                continue
        
        # 生成信号唯一标识
        signal_id = f"{symbol}_{signal_time.strftime('%Y-%m-%d %H:%M:%S')}_{signal['signal_type']}"
        
        # 检查是否是新信号（不在历史记录中）
        is_new_signal = signal_id not in history[symbol]
        
        # 检查时间是否比历史信号新
        is_time_newer = True
        if latest_signal_time and signal_time <= latest_signal_time:
            is_time_newer = False
        
        # 记录所有新信号
        if is_new_signal and is_time_newer:
            logging.info(f"🎯 发现新信号: {symbol} - {signal['signal_type']} - {signal_time}")
            new_signals.append({
                'signal': signal,
                'signal_id': signal_id,
                'signal_time': signal_time
            })
            
            # 更新最新信号时间
            if not latest_signal_time or signal_time > latest_signal_time:
                latest_signal_time = signal_time
        
        elif is_new_signal and not is_time_newer:
            logging.info(f"⚠️  发现重复时间信号，跳过: {signal_id}")
    
    # 处理收集到的新信号
    if new_signals:
        logging.info(f"📊 共收集到 {len(new_signals)} 个新信号")
        
        # 如果信号按时间顺序排列，直接取最后一条；否则排序后取最后一条
        if len(new_signals) > 1:
            # 检查是否需要排序（确保按时间升序）
            is_sorted = all(new_signals[i]['signal_time'] <= new_signals[i+1]['signal_time'] 
                          for i in range(len(new_signals)-1))
            
            if not is_sorted:
                # 按时间排序（从旧到新）
                new_signals.sort(key=lambda x: x['signal_time'])
                logging.info("🔄 新信号已按时间排序")
        
        # 只发送最新的一条信号
        latest_signal_info = new_signals[-1]
        latest_signal = latest_signal_info['signal']
        
        if not is_first and receiver_email:
            # 发送三重滤网信号通知
            signal_info = latest_signal.copy()
            signal_info['symbol'] = symbol
            symbol_name = None
            if symbol and symbol_to_name_dict:
                symbol_name = symbol_to_name_dict.get(symbol)
            signal_info['symbol_name'] = symbol_name
            
            logging.info(f"三重过滤信号： {signal_info}")
            
            # 注册到唐奇安监控器（只注册LONG和SHORT信号）
            if latest_signal['signal_type'] in ['LONG', 'SHORT']:
                donchian_monitor.register_signal(latest_signal, symbol, symbol_name)
                logging.info(f"✅ 已注册到唐奇安监控器，有效期1小时")
            
            # 发送邮件通知
            # send_email_notification(symbol, latest_signal, receiver_email)
            logging.info(f"📤 已发送最新信号: {latest_signal_info['signal_id']}")
        
        # 将所有新信号记录到历史
        for signal_info in new_signals:
            history[symbol].append(signal_info['signal_id'])
        
        # 只保留最近50个信号记录
        if len(history[symbol]) > 50:
            history[symbol] = history[symbol][-50:]
        
        save_signal_history(history)
        logging.info(f"📝 已将所有 {len(new_signals)} 个新信号记录到历史")
        
        return len(new_signals)
    else:
        logging.info(f"📭 没有发现新信号")
        return 0

def scheduled_signal_generation(symbols, gso=True, receiver_email=None):
    """定时信号生成函数（改进版）"""
    logging.info(f"📈 开始分析 {len(symbols)} 个品种...")
    
    all_new_signals = 0
    analyzed_count = 0
    error_count = 0
    
    for symbol in symbols:
        logging.info(f"\n🔍 分析品种 ({analyzed_count + 1}/{len(symbols)}): {symbol}")
        try:
            result = run_strategy_with_three_timeframes(symbol=symbol, generate_signals_only=gso)
            analyzed_count += 1
            
            if result and result['recent_signals']:
                # 检查新信号
                new_signals = check_new_signals(symbol, result['recent_signals'], receiver_email)
                all_new_signals += new_signals
                
                if new_signals > 0:
                    logging.info(f"🎯 {symbol} 发现 {new_signals} 个新信号")
                    logging.info(f"信号内容：{result['recent_signals']}")
                else:
                    # 显示最新信号时间
                    latest_signal = result['recent_signals'][0] if result['recent_signals'] else None
                    if latest_signal:
                        signal_time = latest_signal['timestamp']
                        if not isinstance(signal_time, str):
                            signal_time = signal_time.strftime('%Y-%m-%d %H:%M:%S')
                        logging.info(f"ℹ️  {symbol} 最新信号时间: {signal_time}")
                
                time.sleep(random.uniform(1, 5))
            else:
                logging.info(f"ℹ️  {symbol} 暂无有效信号")
                
        except Exception as e:
            error_count += 1
            logging.error(f"❌ {symbol} 分析失败: {e}")
    
    # 总结报告
    logging.info(f"\n📊 分析总结:")
    logging.info(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logging.info(f"   成功分析: {analyzed_count}/{len(symbols)} 个品种")
    if error_count > 0:
        logging.warning(f"   分析失败: {error_count} 个品种")
        
    logging.info(f"   发现新信号: {all_new_signals} 个")
    
    if all_new_signals == 0:
        logging.info("📭 本次检查未发现新信号")
    else:
        logging.info(f"🎉 本次共发现 {all_new_signals} 个新信号")

def monitor_donchian_breakouts():
    """监控唐奇安通道突破"""
    logging.info("🎯 开始唐奇安通道突破监控...")
    
    # 清理过期信号
    donchian_monitor.cleanup_expired_signals()
    
    # 检查活跃信号数量
    active_count = donchian_monitor.get_active_signal_count()
    if active_count == 0:
        logging.info("📭 当前没有活跃的唐奇安监控信号")
        return
    
    logging.info(f"🔍 当前有 {active_count} 个活跃信号需要监控")
    
    # 监控所有活跃信号
    donchian_monitor.monitor_all_active_signals()

def scheduled_day_trading_task(symbols, gso=True, receiver_email=None, interval=5, donchian_interval=1):
    """定时交易任务"""
    logging.info(f"🚀 启动定时监控任务")
    logging.info(f"📈 监控品种: {', '.join(symbols)}")
    logging.info(f"⏰ 三重滤网检查间隔: {interval} 分钟")
    logging.info(f"🎯 唐奇安监控间隔: {donchian_interval} 分钟")
    logging.info(f"📧 邮件通知: {'开启' if receiver_email else '关闭'}")
    logging.info("⏹️  按 Ctrl+C 停止监控")
    
    # 立即执行一次
    scheduled_signal_generation(symbols, gso, receiver_email)
    monitor_donchian_breakouts()
    
    # 设置定时任务
    schedule.every(interval).minutes.do(
        scheduled_signal_generation, symbols, gso, receiver_email
    )
    
    schedule.every(donchian_interval).minutes.do(monitor_donchian_breakouts)
    
    # 每小时清理一次过期信号
    schedule.every().hour.do(donchian_monitor.cleanup_expired_signals)
    
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("\n🛑 监控任务已停止")

def get_symbols(args):
    """根据参数获取品种列表"""
    if args.file:
        # 从Excel文件读取
        config_file = args.symbol_config_file
        symbols = load_symbols_from_excel(config_file)
        if not symbols:
            logging.info("❌ 无法从文件读取品种列表，请检查配置文件")
            sys.exit(1)
        return symbols
    elif args.symbol:
        # 从命令行参数读取
        symbols = [s.strip() for s in args.symbol.split(',')]
        symbols = [s for s in symbols if s]
        return symbols
    else:
        logging.error("❌ 请提供品种参数 --symbol 或使用 --file 从文件读取")
        sys.exit(1)

def init_logging():
    """全局日志配置（在策略初始化前调用）"""
    log_format = '%(asctime)s [%(levelname)s] %(message)s'
    log_file = 'logs/day_trading_plus.log'
    
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


'''
# 从配置文件运行
python day_trading_system_ex.py --file --exec schedule --interval 3

# 测试单个品种
python day_trading_system_ex.py --symbol FG2605 --exec test

# 自定义唐奇安周期
python day_trading_system_ex.py --file --exec schedule --donchian_period 30
'''
if __name__ == "__main__":
    load_dotenv()
    init_logging()
    args = parse_args()

    # 获取品种列表
    symbols = get_symbols(args)
    
    exec_mode = args.exec
    gso_bool = args.gso.lower() in ['true', '1']
    receiver_email = args.email
    
    # 可选：限制测试品种数量
    # symbols = symbols[:1]
    
    logging.info(f"📈 交易品种: {', '.join(symbols)}")
    logging.info(f"🎯 执行模式: {exec_mode}")
    logging.info(f"🔔 仅生成信号: {gso_bool}")
    logging.info(f"📧 邮件通知: {receiver_email if receiver_email else '未设置'}")
    logging.info(f"🎯 唐奇安通道周期: {args.donchian_period}")
    
    # 更新唐奇安监控器周期
    donchian_monitor.period = args.donchian_period
    
    if exec_mode == 'schedule':
        scheduled_day_trading_task(
            symbols=symbols, 
            gso=gso_bool, 
            receiver_email=receiver_email,
            interval=args.interval,
            donchian_interval=1  # 唐奇安监控每分钟检查一次
        )
    else:
        # 测试模式
        if symbols:
            symbol = symbols[0]
            logging.info(f"🧪 测试模式 - 分析品种: {symbol}")
            result = run_strategy_with_three_timeframes(
                symbol=symbol, 
                generate_signals_only=gso_bool
            )
            
            if result and result['recent_signals']:
                # 注册到唐奇安监控器
                latest_signal = result['recent_signals'][0]
                if latest_signal['signal_type'] in ['LONG', 'SHORT']:
                    symbol_name = symbol_to_name_dict.get(symbol) if symbol_to_name_dict else None
                    donchian_monitor.register_signal(latest_signal, symbol, symbol_name)
                    
                    # 立即检查突破
                    ttime.sleep(2)  # 等待数据加载
                    monitor_donchian_breakouts()