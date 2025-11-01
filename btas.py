import logging
from logging.handlers import TimedRotatingFileHandler
import os
import backtrader as bt
import pandas as pd
import akshare as ak
from datetime import datetime
from my_backtrader.tts import TripleScreenTradingSystem
import concurrent.futures
from typing import List, Dict, Any
import warnings
from pathlib import Path
warnings.filterwarnings('ignore')

# 自定义数据feed（保持与您原有代码一致）
class FuturesDataFeed(bt.feeds.PandasData):
    """适配期货数据的Backtrader数据源"""
    params = (
        ('datetime', '日期'),
        ('open', '开盘价'),
        ('high', '最高价'),
        ('low', '最低价'),
        ('close', '收盘价'),
        ('volume', '成交量'),
        ('openinterest', '持仓量'),
    )

# 批量趋势分析系统
class BatchTrendAnalysisSystem:
    """
    批量期货商品趋势分析系统
    """
    
    def __init__(self, start_date='20230101', end_date=None, max_workers=5):
        self.start_date = start_date
        self.end_date = end_date or datetime.now().strftime('%Y%m%d')
        self.max_workers = max_workers
        self.logger = logging.getLogger('BatchTrendAnalysis')
        self.all_reports = []
        
    def get_main_contracts(self) -> pd.DataFrame:
        """获取主力合约列表"""
        self.logger.info("正在获取当前主力合约列表...")
        try:
            main_contracts_df = ak.futures_display_main_sina()
            self.logger.info(f"成功获取 {len(main_contracts_df)} 个主力合约")
            return main_contracts_df
        except Exception as e:
            self.logger.error(f"获取主力合约失败: {e}")
            # 返回示例数据用于测试
            return pd.DataFrame({
                'symbol': ['SA0', 'MA0', 'FG0', 'TA0', 'RM0'],
                'name': ['纯碱连续', '甲醇连续', '玻璃连续', 'PTA连续', '菜粕连续']
            })

    def get_contract_data(self, symbol: str, symbol_name: str) -> Dict[str, Any]:
        """获取单个合约的数据"""
        try:
            self.logger.info(f"正在获取 {symbol_name}({symbol}) 的历史数据...")
            
            # 获取日线数据
            daily_df = ak.futures_main_sina(symbol=symbol, start_date=self.start_date)
            if daily_df.empty:
                self.logger.warning(f"{symbol_name}({symbol}) 日线数据为空")
                return None
                
            daily_df['日期'] = pd.to_datetime(daily_df['日期'])
            daily_df = daily_df.sort_values('日期')
            # print(f"======日数据====={self.start_date}=====")
            # print(daily_df.head())
            # print(daily_df.tail())
            
            # 获取周线数据
            weekly_df = self.futures_main_weekly_sina(daily_df= daily_df, symbol=symbol, start_date=self.start_date)
            if weekly_df.empty:
                self.logger.warning(f"{symbol_name}({symbol}) 周线数据为空")
                return None
            
            # print("======周数据==========")
            # print(weekly_df.head())
            # print(weekly_df.tail())
                
            weekly_df['日期'] = pd.to_datetime(weekly_df['日期'])
            weekly_df = weekly_df.sort_values('日期')
            
            return {
                'symbol': symbol,
                'name': symbol_name,
                'daily_data': daily_df,
                'weekly_data': weekly_df
            }
            
        except Exception as e:
            self.logger.error(f"获取 {symbol_name}({symbol}) 数据失败: {e}")
            return None

    def futures_main_weekly_sina(
        self, 
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
        if daily_df is None:
            daily_df = ak.futures_main_sina(symbol=symbol, start_date=start_date, end_date=end_date)    
        else:
            daily_df = daily_df.copy()   
        daily_df["日期"] = pd.to_datetime(daily_df["日期"])
        daily_df.set_index("日期", inplace=True)
        
        # 聚合逻辑：每周一至周五为一周，取首开、最高、最低、尾收、成交量和持仓量总和
        weekly_df = daily_df.resample("W-FRI").agg({
            "开盘价": "first",
            "最高价": "max",
            "最低价": "min",
            "收盘价": "last",
            "成交量": "sum",
            "持仓量": "sum",
            "动态结算价": "last"
        }).dropna()
        
        # 2. 日期筛选
        weekly_df = weekly_df[(weekly_df.index >= pd.to_datetime(start_date)) & 
                            (weekly_df.index <= pd.to_datetime(end_date))]
        weekly_df.reset_index(inplace=True)
        weekly_df.rename(columns={"index": "日期"}, inplace=True)
        return weekly_df

    def analyze_single_contract(self, contract_data: Dict[str, Any]) -> Dict[str, Any]:
        """分析单个合约的趋势"""
        symbol = contract_data['symbol']
        symbol_name = contract_data['name']
        
        try:
            self.logger.info(f"开始分析 {symbol_name}({symbol})...")
            
            # 创建cerebro实例
            cerebro = bt.Cerebro()
            cerebro.addstrategy(TripleScreenTradingSystem, printlog=False, symbol = symbol)  # 关闭详细日志
            cerebro.broker.setcash(100000.0)
            cerebro.broker.setcommission(commission=0.0005)
            
            # 添加数据
            print(contract_data['daily_data'].tail())
            print(contract_data['weekly_data'].tail())
            daily_data = FuturesDataFeed(dataname=contract_data['daily_data'])
            weekly_data = FuturesDataFeed(dataname=contract_data['weekly_data'])
            
            cerebro.adddata(daily_data, name=f"{symbol_name}")
            cerebro.adddata(weekly_data, name=f"{symbol_name}_WEEKLY")
            # 运行分析（不进行实际交易）
            strategies = cerebro.run()
            strategy = strategies[0]

            # 获取分析报告
            if strategy.analysis_reports:
                latest_report = strategy.analysis_reports[-1]
                
                # 添加额外信息
                latest_report['analysis_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                latest_report['data_period'] = f"{contract_data['daily_data']['日期'].min().strftime('%Y-%m-%d')} 至 {contract_data['daily_data']['日期'].max().strftime('%Y-%m-%d')}"
                latest_report['data_points'] = len(contract_data['daily_data'])
                
                self.logger.info(f"✅ {symbol_name}({symbol}) 分析完成")
                return latest_report
            else:
                self.logger.warning(f"⚠️ {symbol_name}({symbol}) 无分析报告")
                return None
                
        except Exception as e:
            self.logger.error(f"❌ 分析 {symbol_name}({symbol}) 失败: {e}")
            return None

    def generate_summary_report(self, reports: List[Dict]) -> pd.DataFrame:
        """生成汇总报告"""
        if not reports:
            self.logger.warning("没有有效的分析报告")
            return pd.DataFrame()
            
        df = pd.DataFrame(reports)
        
        # 添加信号强度分类
        def classify_signal(strength):
            if strength >= 80:
                return "强烈"
            elif strength >= 60:
                return "中等" 
            elif strength >= 40:
                return "弱"
            else:
                return "无"
        
        df['信号强度分类'] = df['signal_strength'].apply(classify_signal)
        
        # 排序：先按信号类型，再按信号强度
        df['信号排序'] = df.apply(lambda x: 
            (0 if x['buy_signal'] == 1 else 1 if x['sell_signal'] == 1 else 2, 
             -x['signal_strength']), axis=1)
        df = df.sort_values('信号排序')
        
        return df

    def ensure_directory_exists(self, file_path):
        """
        确保文件路径中的目录存在，如果不存在则创建（支持多级嵌套目录）
        """
        # 使用 pathlib 更可靠地处理路径
        path = Path(file_path)
        
        # 创建所有父目录（如果不存在）
        path.parent.mkdir(parents=True, exist_ok=True)
        return True

    def save_reports(self, summary_df: pd.DataFrame, detailed_reports: List[Dict]):
        """保存报告到文件"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dir = f"reports/report_{timestamp}"
        self.ensure_directory_exists(f"{dir}/1.txt")
        
        # 保存汇总报告
        if not summary_df.empty:
            summary_file = f"{dir}/trend_analysis_summary_{timestamp}.csv"
            summary_df.to_csv(summary_file, index=False, encoding='utf-8-sig')
            self.logger.info(f"汇总报告已保存: {summary_file}")
            
            # 保存详细报告
            detailed_file = f"{dir}/trend_analysis_detailed_{timestamp}.csv"
            detailed_df = pd.DataFrame(detailed_reports)
            detailed_df.to_csv(detailed_file, index=False, encoding='utf-8-sig')
            self.logger.info(f"详细报告已保存: {detailed_file}")
            
            # 生成HTML报告
            self.generate_html_report(summary_df, detailed_reports, timestamp, dir)
        else:
            self.logger.warning("没有数据可保存")

    def generate_html_report(self, summary_df: pd.DataFrame, detailed_reports: List[Dict], timestamp: str, dir: str):
        """生成HTML格式的可视化报告"""
        try:
            html_file = f"{dir}/trend_analysis_report_{timestamp}.html"
            
            # 信号统计
            buy_signals = len(summary_df[summary_df['buy_signal'] == 1])
            sell_signals = len(summary_df[summary_df['sell_signal'] == 1])
            total_contracts = len(summary_df)
            
            # 生成HTML内容
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>期货趋势分析报告</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    .header {{ background: #f4f4f4; padding: 20px; border-radius: 5px; }}
                    .summary {{ background: #e8f4fd; padding: 15px; margin: 10px 0; border-radius: 5px; }}
                    .signal-buy {{ background: #d4edda; }}
                    .signal-sell {{ background: #f8d7da; }}
                    .signal-none {{ background: #fff3cd; }}
                    table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
                    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                    th {{ background-color: #f2f2f2; }}
                    .strong {{ color: #28a745; font-weight: bold; }}
                    .medium {{ color: #ffc107; }}
                    .weak {{ color: #fd7e14; }}
                </style>
            </head>
            <body>
                <div class="header">
                    <h1>📊 期货趋势分析报告</h1>
                    <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    <p>分析合约数量: {total_contracts}</p>
                </div>
                
                <div class="summary">
                    <h2>📈 信号统计</h2>
                    <p>买入信号: <strong>{buy_signals}</strong> 个</p>
                    <p>卖出信号: <strong>{sell_signals}</strong> 个</p>
                    <p>无信号: <strong>{total_contracts - buy_signals - sell_signals}</strong> 个</p>
                </div>
                
                <h2>📋 详细分析结果</h2>
                <table>
                    <thead>
                        <tr>
                            <th>商品</th>
                            <th>商品符号</th>
                            <th>趋势</th>
                            <th>信号</th>
                            <th>信号强度</th>
                            <th>收盘价</th>
                            <th>市场强度</th>
                            <th>持仓量状态</th>
                            <th>ATR相对百分比</th>
                            <th>分析时间</th>
                        </tr>
                    </thead>
                    <tbody>
            """
            
            for _, row in summary_df.iterrows():
                signal_class = "signal-buy" if row['buy_signal'] == 1 else "signal-sell" if row['sell_signal'] == 1 else "signal-none"
                signal_text = "买入" if row['buy_signal'] == 1 else "卖出" if row['sell_signal'] == 1 else "无"
                strength_class = "strong" if row['signal_strength'] >= 80 else "medium" if row['signal_strength'] >= 60 else "weak"
                
                html_content += f"""
                        <tr class="{signal_class}">
                            <td><strong>{row['symbol_name']}</strong></td>
                            <td>{row['symbol']}</td>
                            <td>{row['trend_text']}</td>
                            <td><strong>{signal_text}</strong></td>
                            <td class="{strength_class}">{row['signal_strength']}% ({row['信号强度分类']})</td>
                            <td>{row['close_price']:.2f}</td>
                            <td>{row['market_strength']}</td>
                            <td>{row['oi_status']}</td>
                            <td>{row['atr_percent']}</td>
                            <td>{row['date']}</td>
                        </tr>
                """
            
            html_content += """
                    </tbody>
                </table>
            </body>
            </html>
            """
            
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
                
            self.logger.info(f"HTML报告已生成: {html_file}")
            
        except Exception as e:
            self.logger.error(f"生成HTML报告失败: {e}")

    def run_analysis(self):
        """运行批量分析"""
        self.logger.info("🚀 开始批量期货趋势分析...")
        
        # 获取主力合约列表
        contracts_df = self.get_main_contracts()
        if contracts_df.empty:
            self.logger.error("无法获取主力合约列表，分析终止")
            return
        print(contracts_df.head())
        
        # 获取合约数据
        self.logger.info("📥 正在获取各合约历史数据...")
        all_contract_data = []
        
        # 使用线程池并行获取数据
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_contract = {}
            
            for _, row in contracts_df.iterrows():
                symbol = row['symbol']
                name = row['name']
                future = executor.submit(self.get_contract_data, symbol, name)
                future_to_contract[future] = (symbol, name)
            
            for future in concurrent.futures.as_completed(future_to_contract):
                symbol, name = future_to_contract[future]
                try:
                    contract_data = future.result()
                    if contract_data:
                        all_contract_data.append(contract_data)
                        self.logger.info(f"✅ 成功获取 {name}({symbol}) 数据")
                    else:
                        self.logger.warning(f"⚠️ 跳过 {name}({symbol}) - 数据获取失败")
                except Exception as e:
                    self.logger.error(f"❌ 处理 {name}({symbol}) 时出错: {e}")
        
        self.logger.info(f"📊 成功获取 {len(all_contract_data)} 个合约的数据")
        
        # 分析每个合约
        self.logger.info("🔍 开始趋势分析...")
        analysis_reports = []
        
        for contract_data in all_contract_data:
            report = self.analyze_single_contract(contract_data)
            if report:
                analysis_reports.append(report)
        
        self.logger.info(f"🎯 分析完成: 成功 {len(analysis_reports)}/{len(all_contract_data)} 个合约")
        
        # 生成报告
        if analysis_reports:
            summary_df = self.generate_summary_report(analysis_reports)
            self.save_reports(summary_df, analysis_reports)
            
            # 打印关键信号
            buy_signals = summary_df[summary_df['buy_signal'] == 1]
            sell_signals = summary_df[summary_df['sell_signal'] == 1]
            
            self.logger.info("\n" + "="*80)
            self.logger.info("🎯 关键交易信号")
            self.logger.info("="*80)
            
            if not buy_signals.empty:
                self.logger.info("📈 买入信号:")
                for _, signal in buy_signals.iterrows():
                    self.logger.info(f"  ✅ {signal['symbol']}: {signal['trend_text']} | 强度:{signal['signal_strength']}% | 价格:{signal['close_price']:.2f}")
            
            if not sell_signals.empty:
                self.logger.info("📉 卖出信号:")
                for _, signal in sell_signals.iterrows():
                    self.logger.info(f"  🔻 {signal['symbol']}: {signal['trend_text']} | 强度:{signal['signal_strength']}% | 价格:{signal['close_price']:.2f}")
                    
            self.logger.info("="*80)
        else:
            self.logger.warning("⚠️ 没有生成任何分析报告")


def init_logging():
    """全局日志配置（在策略初始化前调用）"""
    log_format = '%(asctime)s [%(levelname)s] %(message)s'
    log_file = 'logs/batch_futures.log'
    
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
    

# 使用示例
if __name__ == "__main__":
    
    init_logging()
    
    # 创建分析系统实例
    analyzer = BatchTrendAnalysisSystem(
        start_date='20230101',  # 开始日期
        max_workers=3           # 并发数，根据网络情况调整
    )
    
    # 运行分析
    analyzer.run_analysis()