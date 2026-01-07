import argparse
import logging
from logging.handlers import TimedRotatingFileHandler
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import sys
from dotenv import load_dotenv

import pandas as pd
from my_backtrader.day_trading_signal_generator import run_strategy_with_signals, print_signals_summary
import schedule
import time
import json
import os

from sql.future_data_manager_mysql import FutureDataManagerMysql
from tool import send_to_dingding

# 信号记录文件路径
SIGNAL_HISTORY_FILE = 'signal_history.json'
# SYMBOLS_CONFIG_FILE = 'symbols_config.xlsx'
#夜盘交易商品
# SYMBOLS_CONFIG_FILE = 'overnight_symbols_config.xlsx'

symbol_to_name_dict = None

# 期货数据管理，mysql版本
fdmm: FutureDataManagerMysql = None




def load_symbols_from_excel(config_file):
    """从Excel文件加载品种配置"""
    try:
        if not os.path.exists(config_file):
            logging.ERROR(f"❌ 品种配置文件 {config_file} 不存在")
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
        k线图指标绘制
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
    parser.add_argument('--interval', type=int, default=5, 
                        help="定时执行间隔(分钟)")
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
RSI: {signal_info['rsi']:.2f}
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
            # print(f"跳过旧信号: {signal_time} <= {latest_signal_time}")
        
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
        # else:
        #     print(f"📭 已知信号: {signal_id}")
    
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
            global symbol_to_name_dict
            send_to_dingding(
                signal=latest_signal,
                symbol=symbol,
                symbol_to_name_dict=symbol_to_name_dict
            )
            signal_info = latest_signal.copy()
            signal_info['symbol'] = symbol
            symbol_name = None
            if symbol and symbol_to_name_dict:
                symbol_name = symbol_to_name_dict.get(symbol)
            signal_info['symbol_name'] = symbol_name
            logging.info(f"最新信号： {signal_info}")
            # global fdmm
            # fdmm.donchian_breakout.register_signal(latest_signal)
            
            send_email_notification(symbol, signal, receiver_email)
            # send_email_notification(symbol, signal, "717480622@qq.com")
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
        logging.error(f"📭 没有发现新信号")
        return 0

def test_day_trading_symbol(symbol='JM2601', gso=True, receiver_email=None):
    '''
        产生信号
    '''
    logging.info(f"\n🔍 开始分析品种: {symbol}")
    result = run_strategy_with_signals(symbol=symbol, generate_signals_only=gso, debug_mode= True)
    
    if result and result['recent_signals']:
        print_signals_summary(result)
        
        # 检查新信号
        new_signals = check_new_signals(symbol, result['recent_signals'], receiver_email)
        
        # 输出性能统计
        logging.info(f"\n📊 性能统计:")
        logging.info(f"初始资金: {result['initial_cash']:.2f}")
        logging.info(f"最终资金: {result['final_cash']:.2f}")
        logging.info(f"总交易次数: {result['total_trades']}")
        logging.info(f"胜率: {result['performance']['win_rate']:.2%}")
        logging.info(f"总信号数: {result['performance']['total_signals']}")
        logging.info(f"新发现信号: {new_signals} 个")
    else:
        logging.error("❌ 未获取到交易信号")

def scheduled_signal_generation(symbols, gso=True, receiver_email=None):
    """定时信号生成函数（改进版）"""
    logging.info(f"📈 开始分析 {len(symbols)} 个品种...")
    
    all_new_signals = 0
    analyzed_count = 0
    error_count = 0
    
    for symbol in symbols:
        logging.info(f"\n🔍 分析品种 ({analyzed_count + 1}/{len(symbols)}): {symbol}")
        try:
            result = run_strategy_with_signals(symbol=symbol, generate_signals_only=gso)
            analyzed_count += 1
            
            if result and result['recent_signals']:
                # 检查新信号
                new_signals = check_new_signals(symbol, result['recent_signals'], receiver_email)
                all_new_signals += new_signals
                
                if new_signals > 0:
                    logging.info(f"🎯 {symbol} 发现 {new_signals} 个新信号")
                    print_signals_summary({'recent_signals': result['recent_signals']})
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

def scheduled_day_trading_task(symbols, gso=True, receiver_email=None, interval=5):
    """定时交易任务"""
    logging.info(f"🚀 启动定时监控任务")
    logging.info(f"📈 监控品种: {', '.join(symbols)}")
    logging.info(f"⏰ 检查间隔: {interval} 分钟")
    logging.info(f"📧 邮件通知: {'开启' if receiver_email else '关闭'}")
    logging.info("⏹️  按 Ctrl+C 停止监控")
    
    # 立即执行一次
    scheduled_signal_generation(symbols, gso, receiver_email)
    
    # 设置定时任务
    schedule.every(interval).minutes.do(scheduled_signal_generation, symbols, gso, receiver_email)
    
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("\n🛑 监控任务已停止")
        
        
'''
# 从文件监控多个品种
# 白盘
python day_trading_system.py --file --exec schedule --email yang.qq123@163.com --symbol_config_file symbols_config.xlsx
# 夜盘
python day_trading_system.py --file --exec schedule --email yang.qq123@163.com --symbol_config_file overnight_symbols_config.xlsx

# 监控单个品种，开启邮件通知
python day_trading_system.py --symbol JM2601 --exec schedule --email your_email@qq.com

# 监控多个品种
python day_trading_system.py --symbol JM2601,SA0,MA0 --exec schedule --email your_email@qq.com

# 设置10分钟检查间隔
python day_trading_system.py --symbol JM2601 --exec schedule --email your_email@qq.com --interval 10

# 单次测试多个品种
python day_trading_system.py --symbol JM2605 --exec test --email your_email@qq.com
'''

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
    log_file = 'logs/day_trading.log'
    
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

if __name__ == "__main__":
    load_dotenv()
    init_logging()
    args = parse_args()
    
    
    # host=os.getenv("DB_HOST")
    # user=os.getenv("DB_USER")
    # password=os.getenv("DB_PASSWORD")
    # database = os.getenv("DB_DATABASE")
    # port=int(os.getenv("DB_PORT")) 

    # logging.info(f"数据库连接信息: host={host}, user={user}, database={database}, port={port}")
    # fd = FutureDataManagerMysql(
    #     host=host,
    #     user=user,
    #     password=password,
    #     database=database,
    #     port=port
    # )
    # res = fd._init_database()
    # if not res:
    #     sys.exit(1)
    
    # fdmm = fd
    
    
    # 获取品种列表
    symbols = get_symbols(args)
    
    exec_mode = args.exec
    gso_bool = args.gso.lower() in ['true', '1']
    receiver_email = args.email
    
    logging.info(f"📈 交易品种: {', '.join(symbols)}")
    logging.info(f"🎯 执行模式: {exec_mode}")
    logging.info(f"🔔 仅生成信号: {gso_bool}")
    logging.info(f"📧 邮件通知: {receiver_email if receiver_email else '未设置'}")
    
    if exec_mode == 'schedule':
        scheduled_day_trading_task(
            symbols=symbols, 
            gso=gso_bool, 
            receiver_email=receiver_email,
            interval=args.interval
        )
    else:
        for symbol in symbols:
            test_day_trading_symbol(
                symbol=symbol, 
                gso=gso_bool, 
                receiver_email=receiver_email
            )