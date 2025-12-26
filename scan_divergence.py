import json
import random
import numpy as np
import pandas as pd
import akshare as ak
import schedule
import time
import os
from datetime import datetime, timedelta
import warnings

from tool import send_markdown_to_dingding

warnings.filterwarnings('ignore')

# ==================== 核心计算函数 ====================
def calculate_macd_futures(df, fast=12, slow=26, signal=9):
    """计算期货MACD指标"""
    if len(df) < slow:
        return df
    
    exp1 = df['close'].ewm(span=fast, adjust=False).mean()
    exp2 = df['close'].ewm(span=slow, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['MACD_Signal'] = df['MACD'].ewm(span=signal, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']
    return df

def detect_futures_divergence(df, lookback_bars=100):
    """
    期货背离检测核心函数
    严格遵循MACD半自动三步法
    """
    signals = []
    
    if len(df) < lookback_bars + 50:
        return pd.DataFrame()
    
    macd_hist = df['MACD_Hist'].values
    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    
    # 步骤1：寻找初始极点
    for i in range(lookback_bars, len(df) - 20):
        # 看涨背离：寻找MACD低点A
        if macd_hist[i] == np.min(macd_hist[i-lookback_bars:i+1]) and macd_hist[i] < 0:
            a_idx = i
            a_price = low[i]
            a_macd = macd_hist[i]
            
            # 步骤2：寻找突破点B (MACD上穿零轴)
            for j in range(a_idx + 1, min(a_idx + 150, len(df))):
                if macd_hist[j] > 0 and macd_hist[j-1] <= 0:
                    b_idx = j
                    
                    # 步骤3：寻找二次低点C
                    for k in range(b_idx + 1, min(b_idx + 150, len(df))):
                        # 价格创新低但MACD未创新低
                        if low[k] < a_price * 0.98 and macd_hist[k] > a_macd * 1.1:
                            # 计算背离强度
                            price_change_pct = (low[k] - a_price) / a_price * 100
                            macd_change = macd_hist[k] - a_macd
                            
                            signals.append({
                                'type': 'bullish',
                                'point_a_time': df.index[a_idx],
                                'point_a_price': a_price,
                                'point_a_macd': a_macd,
                                'point_b_time': df.index[b_idx],
                                'point_c_time': df.index[k],
                                'point_c_price': low[k],
                                'point_c_macd': macd_hist[k],
                                'signal_time': df.index[k],
                                'current_price': close[k],
                                'price_change_pct': round(price_change_pct, 2),
                                'macd_change': round(macd_change, 4),
                                'divergence_strength': round(abs(macd_change / price_change_pct * 100), 2) if price_change_pct != 0 else 0
                            })
                            break
                    break
        
        # 看跌背离：寻找MACD高点X
        if macd_hist[i] == np.max(macd_hist[i-lookback_bars:i+1]) and macd_hist[i] > 0:
            x_idx = i
            x_price = high[i]
            x_macd = macd_hist[i]
            
            # 寻找跌破点Y (MACD下穿零轴)
            for j in range(x_idx + 1, min(x_idx + 150, len(df))):
                if macd_hist[j] < 0 and macd_hist[j-1] >= 0:
                    y_idx = j
                    
                    # 寻找二次高点Z
                    for k in range(y_idx + 1, min(y_idx + 150, len(df))):
                        # 价格创新高但MACD未创新高
                        if high[k] > x_price * 1.02 and macd_hist[k] < x_macd * 0.9:
                            price_change_pct = (high[k] - x_price) / x_price * 100
                            macd_change = x_macd - macd_hist[k]
                            
                            signals.append({
                                'type': 'bearish',
                                'point_x_time': df.index[x_idx],
                                'point_x_price': x_price,
                                'point_x_macd': x_macd,
                                'point_y_time': df.index[y_idx],
                                'point_z_time': df.index[k],
                                'point_z_price': high[k],
                                'point_z_macd': macd_hist[k],
                                'signal_time': df.index[k],
                                'current_price': close[k],
                                'price_change_pct': round(price_change_pct, 2),
                                'macd_change': round(macd_change, 4),
                                'divergence_strength': round(abs(macd_change / price_change_pct * 100), 2) if price_change_pct != 0 else 0
                            })
                            break
                    break
    
    return pd.DataFrame(signals) if signals else pd.DataFrame()

# ==================== 数据获取与扫描函数 ====================
def get_futures_data(symbol, interval='60'):
    """
    获取期货分钟数据
    :param symbol: 期货合约代码，如 'TA2405' 或 'rb2405'
    :param interval: '1' (1分钟), '5' (5分钟), '15' (15分钟), '30' (30分钟), '60' (60分钟)
    """
    try:
        df = ak.futures_zh_minute_sina(symbol=symbol, period=interval)
        
        if df.empty:
            print(f"  ⚠️  {symbol} 无数据")
            return pd.DataFrame()
        
        # 数据预处理
        df['datetime'] = pd.to_datetime(df['datetime'])
        df = df.sort_values('datetime')
        
        # 重命名列以统一格式
        df.columns = ['datetime', 'open', 'high', 'low', 'close', 'volume', 'open_interest']
        df.set_index('datetime', inplace=True)
        
        return df
        
    except Exception as e:
        print(f"  获取 {symbol} 数据失败: {e}")
        return pd.DataFrame()

def scan_single_futures(symbol, interval='60'):
    """
    扫描单个期货品种的背离信号
    """
    # print(f"  扫描 {symbol} ({interval}分钟)...", end=" ")
    
    # 获取数据
    df = get_futures_data(symbol, interval)
    
    if df.empty or len(df) < 150:
        # print("数据不足")
        return pd.DataFrame()
    
    # 计算MACD
    df = calculate_macd_futures(df)
    
    # 检测背离
    signals = detect_futures_divergence(df, lookback_bars=100)
    
    if not signals.empty:
        signals['symbol'] = symbol
        signals['interval'] = f"{interval}分钟"
        # print(f"发现 {len(signals)} 个信号")
        return signals
    else:
        # print("无信号")
        return pd.DataFrame()

# ==================== 报告生成功能 ====================
class FuturesDivergenceReporter:
    """期货背离报告生成器"""
    
    def __init__(self, symbols_config_file="symbols_config.xlsx"):
        self.symbols = []
        self.symbol_to_name_dict = {}
        self.latest_signals = pd.DataFrame()  # 存储每个合约的最新信号
        
        # 加载品种配置
        self.load_symbols_from_excel(symbols_config_file)
        
        # 创建报告目录
        os.makedirs("divergence_reports", exist_ok=True)
    
    def load_symbols_from_excel(self, config_file):
        """从Excel文件加载品种配置"""
        try:
            if not os.path.exists(config_file):
                print(f"❌ 品种配置文件 {config_file} 不存在")
                return
            
            df = pd.read_excel(config_file)
            
            if 'symbol' not in df.columns:
                print("❌ Excel文件中缺少 'symbol' 列")
                return
            
            # 加载symbol列表
            self.symbols = df['symbol'].dropna().tolist()
            
            # 加载品种名称映射
            if 'name' in df.columns:
                self.symbol_to_name_dict = df.set_index('symbol')['name'].to_dict()
            
            print(f"✅ 从Excel加载了 {len(self.symbols)} 个品种")
            
        except Exception as e:
            print(f"❌ 读取品种配置文件失败: {e}")
    
    def scan_all_futures(self, intervals=['60', '30']):
        """扫描所有期货品种的背离信号"""
        print(f"\n{'='*60}")
        print(f"📊 开始扫描背离信号 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"品种数量: {len(self.symbols)} | 周期: {[f'{i}分钟' for i in intervals]}")
        print('='*60)
        
        all_signals_list = []
        start_time = time.time()
        
        # 遍历所有品种和周期
        for idx, symbol in enumerate(self.symbols, 1):
            print(f"  [{idx}/{len(self.symbols)}] 扫描 {symbol}...")
            for interval in intervals:
                signals = scan_single_futures(symbol, interval)
                time.sleep(random.uniform(1, 5))  # 降低延迟，加快扫描速度
                if not signals.empty:
                    # 添加品种名称
                    if symbol in self.symbol_to_name_dict:
                        signals['symbol_name'] = self.symbol_to_name_dict[symbol]
                    else:
                        signals['symbol_name'] = symbol
                    
                    all_signals_list.append(signals)
        
        scan_duration = time.time() - start_time
        
        if all_signals_list:
            # 合并所有信号
            all_signals = pd.concat(all_signals_list, ignore_index=True)
            
            # 按signal_time排序，获取每个合约的最新信号
            self.extract_latest_signals(all_signals)
            
            # 生成报告
            self.generate_report()
            
            # 显示统计信息
            self.display_statistics(scan_duration)
            
        else:
            print(f"\n📭 本次扫描未发现任何背离信号")
            print(f"⏱️  扫描耗时: {scan_duration:.1f}秒")
        
        return self.latest_signals
    
    def extract_latest_signals(self, all_signals):
        """提取每个合约的最新信号（仅当天）"""
        # 获取今天的日期
        today_date = datetime.now().date()
        
        # 过滤出今天的信号
        today_signals = all_signals[
            all_signals['signal_time'].dt.date == today_date
        ]
        
        if today_signals.empty:
            self.latest_signals = pd.DataFrame()
            return
        
        # 按symbol和interval分组，获取每组的最新信号（signal_time最新的）
        latest_signals_list = []
        
        for (symbol, interval), group in today_signals.groupby(['symbol', 'interval']):
            # 按signal_time降序排序，取第一个（最新的）
            latest = group.sort_values('signal_time', ascending=False).iloc[0]
            latest_signals_list.append(latest)
        
        if latest_signals_list:
            self.latest_signals = pd.DataFrame(latest_signals_list)
            
            # 简化信号信息，只保留需要的字段
            self.latest_signals = self.latest_signals[[
                'symbol', 'symbol_name', 'interval', 'type', 
                'signal_time', 'current_price', 'divergence_strength'
            ]].copy()
            
            # 按signal_time排序，最新的在前面
            self.latest_signals = self.latest_signals.sort_values('signal_time', ascending=False)
        else:
            self.latest_signals = pd.DataFrame()
    
    def _format_report(self):
        """格式化报告内容为Markdown格式"""
        report_lines = []
        
        # 获取今天的日期
        today_date = datetime.now().date()
        
        # 过滤出今天的信号
        today_signals = self.latest_signals[
            self.latest_signals['signal_time'].dt.date == today_date
        ]
        
        if today_signals.empty:
            report_lines.append(f"# 📊 期货背离信号报告")
            report_lines.append(f"\n**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            report_lines.append(f"\n**报告日期**: {today_date}")
            report_lines.append("\n---")
            report_lines.append("\n## 📭 今日暂无背离信号")
            report_lines.append(f"\n未发现{datetime.now().strftime('%Y年%m月%d日')}的背离信号")
            return "\n".join(report_lines)
        
        # 报告头部 - 使用Markdown标题
        report_lines.append(f"# 📊 期货背离信号报告")
        report_lines.append(f"\n**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append(f"\n**报告日期**: {today_date}")
        report_lines.append(f"\n**信号总数**: {len(today_signals)}")
        report_lines.append("\n---")
        
        # 按背离类型分组
        bullish_signals = today_signals[today_signals['type'] == 'bullish']
        bearish_signals = today_signals[today_signals['type'] == 'bearish']
        
        # 看涨背离 - 按品种和周期分组
        if not bullish_signals.empty:
            report_lines.append("\n## 📈 看涨背离信号")
            
            # 按品种和周期分组
            bullish_grouped = bullish_signals.groupby(['symbol', 'symbol_name', 'interval'])
            
            for (symbol, symbol_name, interval), group in bullish_grouped:
                report_lines.append(f"\n### 🔸 {symbol_name} ({symbol}) - {interval}")
                report_lines.append("\n| 信号时间 | 当前价格 | 背离强度 |")
                report_lines.append("| :--- | :--- | :--- |")
                
                for idx, signal in group.iterrows():
                    strength = signal['divergence_strength']
                    strength_icon = "🔥" if strength > 50 else "⭐"
                    strength_display = f"{strength:.1f} {strength_icon}"
                    
                    report_lines.append(
                        f"| {signal['signal_time'].strftime('%H:%M')} | "
                        f"{signal['current_price']} | {strength_display} |"
                    )
        
        # 看跌背离 - 按品种和周期分组
        if not bearish_signals.empty:
            report_lines.append("\n## 📉 看跌背离信号")
            
            # 按品种和周期分组
            bearish_grouped = bearish_signals.groupby(['symbol', 'symbol_name', 'interval'])
            
            for (symbol, symbol_name, interval), group in bearish_grouped:
                report_lines.append(f"\n### 🔹 {symbol_name} ({symbol}) - {interval}")
                report_lines.append("\n| 信号时间 | 当前价格 | 背离强度 |")
                report_lines.append("| :--- | :--- | :--- |")
                
                for idx, signal in group.iterrows():
                    strength = signal['divergence_strength']
                    strength_icon = "🔥" if strength > 50 else "⭐"
                    strength_display = f"{strength:.1f} {strength_icon}"
                    
                    report_lines.append(
                        f"| {signal['signal_time'].strftime('%m-%d %H:%M')} | "
                        f"{signal['current_price']} | {strength_display} |"
                    )
        
        # 统计信息 - 使用列表格式
        report_lines.append("\n## 📋 统计摘要")
        report_lines.append(f"\n- **总信号数**: {len(today_signals)}")
        report_lines.append(f"- **看涨背离**: {len(bullish_signals)}")
        report_lines.append(f"- **看跌背离**: {len(bearish_signals)}")
        
        # 按品种统计
        symbol_counts = today_signals.groupby(['symbol', 'symbol_name']).size()
        report_lines.append("\n- **品种分布**:")
        for (symbol, symbol_name), count in symbol_counts.items():
            report_lines.append(f"  - {symbol_name} ({symbol}): {count}个信号")
        
        # 按周期统计
        interval_counts = today_signals['interval'].value_counts()
        report_lines.append("\n- **周期分布**:")
        for interval, count in interval_counts.items():
            report_lines.append(f"  - {interval}: {count}个信号")
        
        # 今日信号时间范围
        earliest = today_signals['signal_time'].min()
        latest = today_signals['signal_time'].max()
        report_lines.append(f"\n- **信号时间范围**:")
        report_lines.append(f"  - 最早: {earliest.strftime('%H:%M')}")
        report_lines.append(f"  - 最新: {latest.strftime('%H:%M')}")
        
        # 背离强度统计
        avg_strength = today_signals['divergence_strength'].mean()
        max_strength = today_signals['divergence_strength'].max()
        min_strength = today_signals['divergence_strength'].min()
        strong_signals = len(today_signals[today_signals['divergence_strength'] > 50])
        
        report_lines.append(f"\n- **强度分析**:")
        report_lines.append(f"  - 平均强度: {avg_strength:.1f}")
        report_lines.append(f"  - 最强信号: {max_strength:.1f}")
        report_lines.append(f"  - 最弱信号: {min_strength:.1f}")
        report_lines.append(f"  - 强背离信号(>50): {strong_signals}个")
        
        # 最强信号排行
        if not today_signals.empty:
            top_signals = today_signals.nlargest(5, 'divergence_strength')
            report_lines.append(f"\n- **最强信号 Top 5**:")
            for idx, signal in top_signals.iterrows():
                symbol_name = signal.get('symbol_name', signal['symbol'])
                signal_type = "📈看涨" if signal['type'] == 'bullish' else "📉看跌"
                strength = signal['divergence_strength']
                strength_icon = "🔥" if strength > 50 else "⭐"
                
                report_lines.append(
                    f"  {idx+1}. {symbol_name} ({signal['interval']}) - {signal_type} - "
                    f"{strength:.1f}{strength_icon} - {signal['signal_time'].strftime('%H:%M')}"
                )
        
        # 说明部分
        report_lines.append("\n---")
        report_lines.append("\n## 📝 说明")
        report_lines.append("""
    1. **报告范围**: 本报告仅显示当日期货合约的最新背离信号  
    2. **强度标记**: 
    - 🔥 表示强度大于50的强背离信号
    - ⭐ 表示强度小于50的一般背离信号  
    3. **时间说明**: 信号时间为K线结束时间（HH:MM格式）
    4. **信号分组**: 相同品种和周期的信号已合并显示
    5. **风险提示**: 背离信号仅供参考，需结合其他技术指标确认
    """)
        
        return "\n".join(report_lines)

    def generate_report(self):
        """生成Markdown格式的报告"""
        if self.latest_signals.empty:
            print("📭 没有背离信号可生成报告")
            return
        
        # 按背离类型分组（在函数内部定义）
        bullish_signals = self.latest_signals[self.latest_signals['type'] == 'bullish']
        bearish_signals = self.latest_signals[self.latest_signals['type'] == 'bearish']
        
        # 生成报告文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        # report_file_txt = f"divergence_reports/latest_signals_{timestamp}.txt"
        report_file_md = f"divergence_reports/latest_signals_{timestamp}.md"
        
        # 生成报告内容
        report_content = self._format_report()
        
        # 保存为Markdown文件
        with open(report_file_md, 'w', encoding='utf-8') as f:
            f.write(report_content)
            
        #发送到钉钉群里
        send_markdown_to_dingding(msg= report_content)
        
        # 同时保存为纯文本文件（兼容性）
        # with open(report_file_txt, 'w', encoding='utf-8') as f:
        #     # 转换为纯文本格式（移除Markdown标记）
        #     text_content = report_content
        #     text_content = text_content.replace('# ', '')
        #     text_content = text_content.replace('## ', '')
        #     text_content = text_content.replace('**', '')
        #     text_content = text_content.replace('| :--- | :--- | :--- | :--- | :--- |', '')
        #     text_content = text_content.replace('|', ' | ')
        #     f.write(text_content)
        
        print(f"📄 Markdown报告已生成: {report_file_md}")
        # print(f"📄 纯文本报告已生成: {report_file_txt}")
        
        # 在控制台输出简化报告
        print("\n" + "="*80)
        print("📋 最新背离信号报告")
        print("="*80)
        
        # 控制台只显示摘要
        print(f"\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"信号总数: {len(self.latest_signals)}")
        
        if not bullish_signals.empty:
            print(f"\n📈 看涨背离: {len(bullish_signals)}个")
            for idx, signal in bullish_signals.head(5).iterrows():  # 只显示前5个
                name = signal.get('symbol_name', signal['symbol'])
                strength = signal['divergence_strength']
                strength_icon = "🔥" if strength > 50 else "⭐"
                print(f"  {name}({signal['interval']}) - {signal['signal_time'].strftime('%H:%M')} - 强度: {strength:.1f}{strength_icon}")
        
        if not bearish_signals.empty:
            print(f"\n📉 看跌背离: {len(bearish_signals)}个")
            for idx, signal in bearish_signals.head(5).iterrows():  # 只显示前5个
                name = signal.get('symbol_name', signal['symbol'])
                strength = signal['divergence_strength']
                strength_icon = "🔥" if strength > 50 else "⭐"
                print(f"  {name}({signal['interval']}) - {signal['signal_time'].strftime('%H:%M')} - 强度: {strength:.1f}{strength_icon}")
        
        print(f"\n📊 完整报告请查看: {report_file_md}")
        
    def display_statistics(self, scan_duration):
            """显示扫描统计信息"""
            print(f"\n✅ 扫描完成!")
            print(f"⏱️  耗时: {scan_duration:.1f}秒")
            print(f"📈 发现 {len(self.latest_signals)} 个合约有背离信号")
            
            # 按类型统计
            bullish_count = len(self.latest_signals[self.latest_signals['type'] == 'bullish'])
            bearish_count = len(self.latest_signals[self.latest_signals['type'] == 'bearish'])
            
            print(f"📊 看涨背离: {bullish_count} 个 | 看跌背离: {bearish_count} 个")
            
            # 按周期统计
            interval_stats = self.latest_signals['interval'].value_counts()
            print(f"📅 周期分布: {dict(interval_stats)}")
            
            # 显示最新信号时间
            if not self.latest_signals.empty:
                latest_time = self.latest_signals['signal_time'].max()
                earliest_time = self.latest_signals['signal_time'].min()
                print(f"🕒 信号时间范围: {earliest_time.strftime('%H:%M')} - {latest_time.strftime('%H:%M')}")
    
    def setup_schedule(self):
        """设置定时扫描任务"""
        # 设置定时扫描（可根据交易时间调整）
        
        # 开盘前扫描
        schedule.every().day.at("08:45").do(self.scan_all_futures)
        
        # 盘中定时扫描
        for minute in [0, 30]:
            schedule.every().hour.at(f":{minute:02d}").do(
                lambda: self.scan_all_futures(intervals=['30', '60'])
            )
        
        # 午间扫描
        schedule.every().day.at("12:30").do(self.scan_all_futures)
        
        # 收盘后扫描
        schedule.every().day.at("15:15").do(self.scan_all_futures)
        
        print("⏰ 定时任务已设置:")
        print("  08:45 - 开盘前扫描")
        print("  每30分钟 - 盘中扫描 (30分钟和60分钟周期)")
        print("  12:30 - 午间扫描")
        print("  15:15 - 收盘后扫描")
    
    def run_scheduled_scans(self):
        """运行定时扫描"""
        print("\n🚀 期货背离定时扫描程序启动")
        print("="*60)
        
        # 首次立即执行一次扫描
        print("\n🎯 执行首次扫描...")
        self.scan_all_futures(intervals=['60', '30', '15', '5'])
        
        # 设置定时任务
        self.setup_schedule()
        
        # 主循环
        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
                
        except KeyboardInterrupt:
            print("\n\n👋 程序已停止")
        except Exception as e:
            print(f"\n❌ 程序运行出错: {e}")

# ==================== 主程序 ====================
if __name__ == "__main__":    
    # 创建报告生成器实例
    reporter = FuturesDivergenceReporter("symbols_config.xlsx")
    
    if not reporter.symbols:
        print("❌ 没有可扫描的品种，请检查symbols_config.xlsx文件")
        print("   文件应包含'symbol'列，可选'name'列")
        exit(1)
    
    # 运行定时扫描
    reporter.run_scheduled_scans()