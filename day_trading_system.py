import argparse
from datetime import datetime
from my_backtrader.day_trading_signal_generator import run_strategy_with_signals, print_signals_summary
import schedule
import time

def parse_args():
    '''
        k线图指标绘制
    '''
    parser = argparse.ArgumentParser(  
        description='日内交易系统')
    parser.add_argument('--symbol', default="", required=True, 
                        help="期货商品编号")
    parser.add_argument('--gso', choices=['true', 'false', 'True', 'False', '1', '0'], 
                        default='true', help="是否只产生信号")
    parser.add_argument('--exec', choices=['test', 'schedule'], required=True, 
                        help="执行模式：test(单个商品测试) 或 schedule(定时执行)")
    return parser.parse_args()

def test_day_trading_symbol(symbol='JM2601', gso=True):
    '''
        产生信号
    '''
    result = run_strategy_with_signals(symbol=symbol, generate_signals_only=gso)
    
    if result:
        print_signals_summary(result)
        
        # 输出性能统计
        print(f"\n性能统计:")
        print(f"初始资金: {result['initial_cash']:.2f}")
        print(f"最终资金: {result['final_cash']:.2f}")
        print(f"总交易次数: {result['total_trades']}")
        print(f"胜率: {result['performance']['win_rate']:.2%}")
        print(f"总信号数: {result['performance']['total_signals']}")
    else:
        print("未获取到交易结果")

def scheduled_signal_generation(symbol='JM2601', gso=True):
    """定时信号生成函数"""
    print(f"\n=== 定时信号生成 {datetime.now()} ===")
    result = run_strategy_with_signals(symbol=symbol, generate_signals_only=gso)
    if result:
        print(f"交易品种: {symbol}")
        print_signals_summary(result)
    else:
        print("未获取到交易信号")
        
def scheduled_day_trading_task(symbol='JM2601', gso=True):
    """定时交易任务"""
    print(f"启动定时任务 - 品种: {symbol}, 仅生成信号: {gso}")
    print("按 Ctrl+C 停止定时任务")
    
    # 立即执行一次
    scheduled_signal_generation(symbol=symbol, gso=gso)
    
    # 每5分钟运行一次
    schedule.every(5).minutes.do(scheduled_signal_generation, symbol=symbol, gso=gso)
    
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n定时任务已停止")

if __name__ == "__main__":
    args = parse_args()
    symbol = args.symbol
    exec_mode = args.exec  # 避免使用exec关键字
    gso_bool = args.gso.lower() in ['true', '1']
    
    print(f"交易品种: {symbol}")
    print(f"执行模式: {exec_mode}")
    print(f"仅生成信号: {gso_bool}")
    
    if exec_mode == 'schedule':
        scheduled_day_trading_task(symbol=symbol, gso=gso_bool)
    else:
        test_day_trading_symbol(symbol=symbol, gso=gso_bool)