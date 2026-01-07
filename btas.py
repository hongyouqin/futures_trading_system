import logging
from logging.handlers import TimedRotatingFileHandler
import os
import random
import time
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
    
    def __init__(self, start_date='20230101', end_date=None, max_workers=2):
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
            # print(contract_data['daily_data'].tail())
            # print(contract_data['weekly_data'].tail())
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
        base_dir = "reports/"
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
            
            #更新最新的杨希报告，始终在base_dir目录下面保持一份最新的报告
            lastest_detailed_file = f"{base_dir}/lastest_trend_analysis.csv"
            lastest_detailed_df = pd.DataFrame(detailed_reports)
            lastest_detailed_df.to_csv(lastest_detailed_file, index=False, encoding='utf-8-sig')
            
            # 生成HTML报告
            self.generate_html_report(summary_df, detailed_reports, timestamp, dir)
        else:
            self.logger.warning("没有数据可保存")

    def generate_html_report(self, summary_df: pd.DataFrame, detailed_reports: List[Dict], timestamp: str, dir: str):
        """生成HTML格式的可视化报告（按市场强度排序）"""
        try:
            html_file = f"{dir}/trend_analysis_report_{timestamp}.html"
            
            # 确保有必要的字段
            summary_df = summary_df.copy()
            
            # 如果缺少market_strength，根据market_strength_score生成
            if 'market_strength' not in summary_df.columns and 'market_strength_score' in summary_df.columns:
                def get_market_strength_text(score):
                    if score == 1:
                        return "市场坚挺"
                    elif score == -1:
                        return "市场疲软"
                    else:
                        return "市场中性"
                summary_df['market_strength'] = summary_df['market_strength_score'].apply(get_market_strength_text)
            
            # 为市场强度添加详细描述
            def enrich_market_strength(row):
                strength = str(row.get('market_strength', ''))
                price_change = row.get('price_change', 0)
                volume_change = row.get('volume_change', 0)
                oi_change = row.get('oi_change', 0)
                
                if "坚挺" in strength:
                    if price_change > 0:
                        return "市场坚挺: 价涨量增仓升" if volume_change > 0 and oi_change > 0 else "市场坚挺"
                    else:
                        return "市场坚挺: 价跌量减仓降" if volume_change < 0 and oi_change < 0 else "市场坚挺"
                elif "疲软" in strength:
                    if price_change > 0:
                        return "市场疲软: 价涨量减仓降" if volume_change < 0 and oi_change < 0 else "市场疲软"
                    else:
                        return "市场疲软: 价跌量增仓升" if volume_change > 0 and oi_change > 0 else "市场疲软"
                return strength
            
            if any(col in summary_df.columns for col in ['price_change', 'volume_change', 'oi_change']):
                summary_df['market_strength'] = summary_df.apply(enrich_market_strength, axis=1)
            
            # 按市场强度排序（坚挺 > 中性 > 疲软）
            def get_market_strength_weight(strength):
                strength_str = str(strength)
                if "坚挺" in strength_str:
                    return 1
                elif "中性" in strength_str:
                    return 2
                elif "疲软" in strength_str:
                    return 3
                return 4
            
            summary_df['market_strength_weight'] = summary_df['market_strength'].apply(get_market_strength_weight)
            summary_df = summary_df.sort_values(['market_strength_weight', 'signal_strength'], ascending=[True, False])
            
            # 统计数据
            total_contracts = len(summary_df)
            
            # 信号统计
            buy_signals = len(summary_df[summary_df['buy_signal'] == 1])
            sell_signals = len(summary_df[summary_df['sell_signal'] == 1])
            
            # 市场强度统计
            strong_count = summary_df['market_strength'].str.contains('坚挺', na=False).sum()
            weak_count = summary_df['market_strength'].str.contains('疲软', na=False).sum()
            neutral_count = total_contracts - strong_count - weak_count
            
            # 生成HTML
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>期货市场分析报告</title>
                <style>
                    :root {{
                        --color-strong: #28a745;
                        --color-neutral: #ffc107;
                        --color-weak: #dc3545;
                        --color-buy: #d4edda;
                        --color-sell: #f8d7da;
                        --color-none: #fff3cd;
                    }}
                    
                    body {{
                        font-family: 'Microsoft YaHei', Arial, sans-serif;
                        margin: 0;
                        padding: 20px;
                        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
                        min-height: 100vh;
                    }}
                    
                    .container {{
                        max-width: 1400px;
                        margin: 0 auto;
                        background: white;
                        border-radius: 15px;
                        box-shadow: 0 10px 30px rgba(0,0,0,0.1);
                        overflow: hidden;
                    }}
                    
                    .header {{
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: white;
                        padding: 30px;
                        text-align: center;
                    }}
                    
                    .header h1 {{
                        margin: 0;
                        font-size: 2.5em;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        gap: 15px;
                    }}
                    
                    .stats-container {{
                        display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                        gap: 20px;
                        padding: 25px;
                        background: #f8f9fa;
                    }}
                    
                    .stat-card {{
                        background: white;
                        border-radius: 10px;
                        padding: 25px;
                        text-align: center;
                        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
                        transition: transform 0.3s ease;
                        position: relative;
                        overflow: hidden;
                    }}
                    
                    .stat-card:hover {{
                        transform: translateY(-5px);
                        box-shadow: 0 8px 15px rgba(0,0,0,0.1);
                    }}
                    
                    .stat-card::before {{
                        content: '';
                        position: absolute;
                        top: 0;
                        left: 0;
                        right: 0;
                        height: 5px;
                    }}
                    
                    .stat-card.strong::before {{ background: var(--color-strong); }}
                    .stat-card.neutral::before {{ background: var(--color-neutral); }}
                    .stat-card.weak::before {{ background: var(--color-weak); }}
                    .stat-card.buy::before {{ background: var(--color-strong); }}
                    .stat-card.sell::before {{ background: var(--color-weak); }}
                    .stat-card.none::before {{ background: var(--color-neutral); }}
                    
                    .stat-card h3 {{
                        margin-top: 0;
                        color: #333;
                        font-size: 1.2em;
                    }}
                    
                    .stat-number {{
                        font-size: 3em;
                        font-weight: bold;
                        margin: 15px 0;
                    }}
                    
                    .stat-percentage {{
                        font-size: 1.2em;
                        color: #666;
                    }}
                    
                    .market-analysis {{
                        padding: 25px;
                        background: white;
                        margin: 20px;
                        border-radius: 10px;
                        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
                    }}
                    
                    .market-analysis h2 {{
                        color: #333;
                        border-bottom: 2px solid #eaeaea;
                        padding-bottom: 10px;
                        margin-top: 0;
                    }}
                    
                    .market-rules {{
                        display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                        gap: 15px;
                        margin-top: 20px;
                    }}
                    
                    .rule-card {{
                        padding: 15px;
                        border-radius: 8px;
                        border-left: 5px solid;
                        background: #f8f9fa;
                    }}
                    
                    .rule-card.strong {{ border-left-color: var(--color-strong); }}
                    .rule-card.weak {{ border-left-color: var(--color-weak); }}
                    
                    .rule-card h4 {{
                        margin-top: 0;
                        display: flex;
                        align-items: center;
                        gap: 8px;
                    }}
                    
                    table {{
                        width: 100%;
                        border-collapse: collapse;
                        margin: 25px 0;
                        background: white;
                        border-radius: 10px;
                        overflow: hidden;
                        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
                    }}
                    
                    th, td {{
                        padding: 15px;
                        text-align: left;
                        border-bottom: 1px solid #eaeaea;
                    }}
                    
                    th {{
                        background: #f8f9fa;
                        font-weight: 600;
                        color: #333;
                        position: sticky;
                        top: 0;
                    }}
                    
                    tr:hover {{
                        background: #f8f9fa;
                    }}
                    
                    .strength-indicator {{
                        display: inline-block;
                        width: 12px;
                        height: 12px;
                        border-radius: 50%;
                        margin-right: 8px;
                    }}
                    
                    .strength-strong {{ background: var(--color-strong); }}
                    .strength-neutral {{ background: var(--color-neutral); }}
                    .strength-weak {{ background: var(--color-weak); }}
                    
                    .signal-cell {{
                        font-weight: bold;
                        padding: 8px 15px;
                        border-radius: 20px;
                        text-align: center;
                        display: inline-block;
                    }}
                    
                    .signal-buy {{
                        background: var(--color-buy);
                        color: #155724;
                    }}
                    
                    .signal-sell {{
                        background: var(--color-sell);
                        color: #721c24;
                    }}
                    
                    .signal-none {{
                        background: var(--color-none);
                        color: #856404;
                    }}
                    
                    .recommendation {{
                        font-size: 0.9em;
                        color: #555;
                        margin-top: 5px;
                        line-height: 1.4;
                    }}
                    
                    .filter-controls {{
                        display: flex;
                        gap: 10px;
                        padding: 20px;
                        background: #f8f9fa;
                        border-radius: 10px;
                        margin: 20px;
                        flex-wrap: wrap;
                    }}
                    
                    .filter-btn {{
                        padding: 10px 20px;
                        border: none;
                        border-radius: 25px;
                        background: white;
                        color: #666;
                        cursor: pointer;
                        font-weight: 500;
                        transition: all 0.3s ease;
                        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                    }}
                    
                    .filter-btn:hover {{
                        transform: translateY(-2px);
                        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
                    }}
                    
                    .filter-btn.active {{
                        background: #007bff;
                        color: white;
                    }}
                    
                    .footer {{
                        text-align: center;
                        padding: 25px;
                        color: #666;
                        background: #f8f9fa;
                        border-top: 1px solid #eaeaea;
                        margin-top: 30px;
                    }}
                    
                    @media (max-width: 768px) {{
                        .stats-container {{
                            grid-template-columns: 1fr;
                        }}
                        
                        .market-rules {{
                            grid-template-columns: 1fr;
                        }}
                        
                        table {{
                            font-size: 0.9em;
                        }}
                        
                        th, td {{
                            padding: 10px;
                        }}
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>📊 期货市场分析报告</h1>
                        <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 分析合约: {total_contracts}个</p>
                    </div>
                    
                    <div class="stats-container">
                        <div class="stat-card strong">
                            <h3>🟢 市场坚挺</h3>
                            <div class="stat-number">{strong_count}</div>
                            <div class="stat-percentage">{strong_count/total_contracts*100:.1f}%</div>
                        </div>
                        
                        <div class="stat-card neutral">
                            <h3>🟡 市场中性</h3>
                            <div class="stat-number">{neutral_count}</div>
                            <div class="stat-percentage">{neutral_count/total_contracts*100:.1f}%</div>
                        </div>
                        
                        <div class="stat-card weak">
                            <h3>🔴 市场疲软</h3>
                            <div class="stat-number">{weak_count}</div>
                            <div class="stat-percentage">{weak_count/total_contracts*100:.1f}%</div>
                        </div>
                        
                        <div class="stat-card buy">
                            <h3>📈 买入信号</h3>
                            <div class="stat-number">{buy_signals}</div>
                            <div class="stat-percentage">{buy_signals/total_contracts*100:.1f}%</div>
                        </div>
                        
                        <div class="stat-card sell">
                            <h3>📉 卖出信号</h3>
                            <div class="stat-number">{sell_signals}</div>
                            <div class="stat-percentage">{sell_signals/total_contracts*100:.1f}%</div>
                        </div>
                        
                        <div class="stat-card none">
                            <h3>⏸️ 无信号</h3>
                            <div class="stat-number">{total_contracts - buy_signals - sell_signals}</div>
                            <div class="stat-percentage">{(total_contracts - buy_signals - sell_signals)/total_contracts*100:.1f}%</div>
                        </div>
                    </div>
                    
                    <div class="market-analysis">
                        <h2>📖 市场强度解读规则</h2>
                        <div class="market-rules">
                            <div class="rule-card strong">
                                <h4><span class="strength-indicator strength-strong"></span>市场坚挺：价涨量增仓升</h4>
                                <p><strong>含义：</strong>上涨趋势健康，买方力量强劲，趋势可能持续</p>
                                <p><strong>建议：</strong>关注做多机会，顺势操作</p>
                            </div>
                            
                            <div class="rule-card strong">
                                <h4><span class="strength-indicator strength-strong"></span>市场坚挺：价跌量减仓降</h4>
                                <p><strong>含义：</strong>下跌趋势健康，空头有序退出，可能接近底部</p>
                                <p><strong>建议：</strong>空头减仓，多头可寻找反弹机会</p>
                            </div>
                            
                            <div class="rule-card weak">
                                <h4><span class="strength-indicator strength-weak"></span>市场疲软：价涨量减仓降</h4>
                                <p><strong>含义：</strong>上涨动力不足，多头获利了结，可能反转</p>
                                <p><strong>建议：</strong>谨慎做多，关注反转信号</p>
                            </div>
                            
                            <div class="rule-card weak">
                                <h4><span class="strength-indicator strength-weak"></span>市场疲软：价跌量增仓升</h4>
                                <p><strong>含义：</strong>下跌加速，新空头入场，趋势可能延续</p>
                                <p><strong>建议：</strong>关注做空机会，但注意风险</p>
                            </div>
                        </div>
                    </div>
                    
                    <div class="filter-controls">
                        <button class="filter-btn active" onclick="filterTable('all')">全部显示</button>
                        <button class="filter-btn" onclick="filterTable('strong')">🟢 市场坚挺</button>
                        <button class="filter-btn" onclick="filterTable('weak')">🔴 市场疲软</button>
                        <button class="filter-btn" onclick="filterTable('buy')">📈 买入信号</button>
                        <button class="filter-btn" onclick="filterTable('sell')">📉 卖出信号</button>
                        <button class="filter-btn" onclick="filterTable('top10')">🏆 前10名</button>
                    </div>
                    
                    <table id="analysis-table">
                        <thead>
                            <tr>
                                <th width="50">排名</th>
                                <th width="100">商品</th>
                                <th width="100">代码</th>
                                <th width="120">市场强度</th>
                                <th width="80">趋势</th>
                                <th width="80">信号</th>
                                <th width="100">信号强度</th>
                                <th width="120">收盘价</th>
                                <th width="120">持仓状态</th>
                                <th width="80">ATR%</th>
                                <th>操作建议</th>
                            </tr>
                        </thead>
                        <tbody>
            """
            
            for idx, (_, row) in enumerate(summary_df.iterrows(), 1):
                # 获取数据
                symbol_name = str(row.get('symbol_name', ''))
                symbol = str(row.get('symbol', ''))
                market_strength = str(row.get('market_strength', '市场中性'))
                trend_text = str(row.get('trend_text', '中性'))
                close_price = row.get('close_price', 0)
                oi_status = str(row.get('oi_status', '正常'))
                atr_percent = row.get('atr_percent', '0.0%')
                signal_strength = row.get('signal_strength', 0)
                
                # 信号判断
                if row.get('buy_signal') == 1:
                    signal_text = "买入"
                    signal_class = "signal-buy"
                    signal_icon = "📈"
                elif row.get('sell_signal') == 1:
                    signal_text = "卖出"
                    signal_class = "signal-sell"
                    signal_icon = "📉"
                else:
                    signal_text = "无"
                    signal_class = "signal-none"
                    signal_icon = "⏸️"
                
                # 市场强度样式
                if "坚挺" in market_strength:
                    strength_class = "strength-strong"
                    strength_icon = "🟢"
                elif "疲软" in market_strength:
                    strength_class = "strength-weak"
                    strength_icon = "🔴"
                else:
                    strength_class = "strength-neutral"
                    strength_icon = "🟡"
                
                # 趋势样式
                if "上涨" in trend_text:
                    trend_class = "trend-up"
                    trend_icon = "↗️"
                elif "下跌" in trend_text:
                    trend_class = "trend-down"
                    trend_icon = "↘️"
                else:
                    trend_class = "trend-neutral"
                    trend_icon = "➡️"
                
                # 信号强度样式
                if signal_strength >= 80:
                    strength_level = "强"
                    strength_color = "color: #28a745; font-weight: bold;"
                elif signal_strength >= 60:
                    strength_level = "中"
                    strength_color = "color: #ffc107; font-weight: bold;"
                else:
                    strength_level = "弱"
                    strength_color = "color: #dc3545; font-weight: bold;"
                
                # 生成操作建议
                recommendation = self._generate_recommendation(row)
                
                html_content += f"""
                            <tr data-strength="{'strong' if '坚挺' in market_strength else 'weak' if '疲软' in market_strength else 'neutral'}" data-signal="{signal_text.lower()}">
                                <td><strong>{idx}</strong></td>
                                <td><strong>{symbol_name}</strong></td>
                                <td><code>{symbol}</code></td>
                                <td>
                                    <span class="strength-indicator {strength_class}"></span>
                                    {strength_icon} {market_strength.split(':')[0] if ':' in market_strength else market_strength}
                                    <div style="font-size: 0.85em; color: #666; margin-top: 2px;">
                                        {market_strength.split(':')[1] if ':' in market_strength and len(market_strength.split(':')) > 1 else ''}
                                    </div>
                                </td>
                                <td>{trend_icon} {trend_text}</td>
                                <td><span class="signal-cell {signal_class}">{signal_icon} {signal_text}</span></td>
                                <td style="{strength_color}">
                                    {signal_strength}% ({strength_level})
                                </td>
                                <td>{close_price:.2f}</td>
                                <td>{oi_status}</td>
                                <td>{atr_percent}</td>
                                <td>
                                    {recommendation}
                                </td>
                            </tr>
                """
            
            html_content += """
                        </tbody>
                    </table>
                    
                    <div class="footer">
                        <p>📋 报告说明</p>
                        <p>1. 市场坚挺表示趋势健康，疲软表示趋势可能反转或存在风险</p>
                        <p>2. 建议结合具体技术分析和风险管理进行操作</p>
                        <p>3. 生成时间: """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """</p>
                        <p style="color: #999; margin-top: 10px;">⚠️ 投资有风险，入市需谨慎</p>
                    </div>
                </div>
                
                <script>
                    function filterTable(type) {{
                        const rows = document.querySelectorAll('#analysis-table tbody tr');
                        const buttons = document.querySelectorAll('.filter-btn');
                        
                        // 更新按钮状态
                        buttons.forEach(btn => {{
                            btn.classList.remove('active');
                            if (btn.textContent.includes(getButtonText(type))) {{
                                btn.classList.add('active');
                            }}
                        }});
                        
                        // 显示数量统计
                        let visibleCount = 0;
                        
                        rows.forEach(row => {{
                            const strength = row.getAttribute('data-strength');
                            const signal = row.getAttribute('data-signal');
                            let showRow = false;
                            
                            switch(type) {{
                                case 'all':
                                    showRow = true;
                                    break;
                                case 'strong':
                                    showRow = strength === 'strong';
                                    break;
                                case 'weak':
                                    showRow = strength === 'weak';
                                    break;
                                case 'buy':
                                    showRow = signal === '买入';
                                    break;
                                case 'sell':
                                    showRow = signal === '卖出';
                                    break;
                                case 'top10':
                                    showRow = row.querySelector('td:first-child strong').textContent <= 10;
                                    break;
                                default:
                                    showRow = true;
                            }}
                            
                            row.style.display = showRow ? '' : 'none';
                            if (showRow) visibleCount++;
                        }});
                        
                        // 更新标题显示数量
                        const header = document.querySelector('.header p');
                        if (header && type !== 'all') {{
                            const originalText = header.textContent.split('|')[0];
                            header.textContent = originalText + ` | 显示: ${{visibleCount}}个`;
                        }}
                    }}
                    
                    function getButtonText(type) {{
                        const texts = {{
                            'all': '全部显示',
                            'strong': '市场坚挺',
                            'weak': '市场疲软',
                            'buy': '买入信号',
                            'sell': '卖出信号',
                            'top10': '前10名'
                        }};
                        return texts[type] || '';
                    }}
                    
                    // 默认显示前10名
                    window.onload = function() {{
                        filterTable('top10');
                    }};
                    
                    // 添加键盘快捷键
                    document.addEventListener('keydown', (e) => {{
                        switch(e.key) {{
                            case '1': filterTable('all'); break;
                            case '2': filterTable('strong'); break;
                            case '3': filterTable('weak'); break;
                            case '4': filterTable('buy'); break;
                            case '5': filterTable('sell'); break;
                            case '0': filterTable('top10'); break;
                        }}
                    }});
                </script>
            </body>
            </html>
            """
            
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
                
            self.logger.info(f"HTML报告已生成: {html_file}")
            return html_file
            
        except Exception as e:
            self.logger.error(f"生成HTML报告失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None


    def _generate_recommendation(self, row):
        """生成具体的操作建议"""
        try:
            market_strength = str(row.get('market_strength', ''))
            trend_text = str(row.get('trend_text', ''))
            
            # 判断买入信号
            is_buy_signal = row.get('buy_signal') == 1
            is_sell_signal = row.get('sell_signal') == 1
            
            # 市场强度判断
            is_strong = "坚挺" in market_strength
            is_weak = "疲软" in market_strength
            
            # 趋势判断
            is_uptrend = "上涨" in trend_text
            is_downtrend = "下跌" in trend_text
            
            # 详细的市场状态
            market_detail = ""
            if "价涨量增仓升" in market_strength:
                market_detail = "（健康上涨）"
            elif "价跌量减仓降" in market_strength:
                market_detail = "（健康下跌）"
            elif "价涨量减仓降" in market_strength:
                market_detail = "（上涨乏力）"
            elif "价跌量增仓升" in market_strength:
                market_detail = "（下跌加速）"
            
            # 生成建议
            if is_strong:
                if is_uptrend:
                    if is_buy_signal:
                        return f"✅ 健康上涨趋势+买入信号，可考虑做多{market_detail}"
                    elif is_sell_signal:
                        return f"⚠️ 健康上涨趋势+卖出信号，逆势风险{market_detail}"
                    else:
                        return f"➖ 健康上涨趋势，等待做多机会{market_detail}"
                elif is_downtrend:
                    if is_sell_signal:
                        return f"✅ 健康下跌趋势+卖出信号，可考虑做空{market_detail}"
                    elif is_buy_signal:
                        return f"⚠️ 健康下跌趋势+买入信号，逆势风险{market_detail}"
                    else:
                        return f"➖ 健康下跌趋势，等待做空机会{market_detail}"
                else:
                    if is_buy_signal:
                        return f"🟢 市场坚挺+买入信号，可轻仓做多{market_detail}"
                    elif is_sell_signal:
                        return f"🟢 市场坚挺+卖出信号，可轻仓做空{market_detail}"
                    else:
                        return f"➖ 市场坚挺，寻找机会{market_detail}"
                        
            elif is_weak:
                if is_uptrend:
                    if is_buy_signal:
                        return f"⚠️ 上涨乏力+买入信号，谨慎做多{market_detail}"
                    elif is_sell_signal:
                        return f"✅ 上涨乏力+卖出信号，可考虑做空{market_detail}"
                    else:
                        return f"➖ 上涨乏力，观望等待{market_detail}"
                elif is_downtrend:
                    if is_sell_signal:
                        return f"⚠️ 下跌加速+卖出信号，谨慎做空{market_detail}"
                    elif is_buy_signal:
                        return f"✅ 下跌加速+买入信号，可考虑做多{market_detail}"
                    else:
                        return f"➖ 下跌加速，观望等待{market_detail}"
                else:
                    if is_buy_signal:
                        return f"🔴 市场疲软+买入信号，需谨慎{market_detail}"
                    elif is_sell_signal:
                        return f"🔴 市场疲软+卖出信号，需谨慎{market_detail}"
                    else:
                        return f"➖ 市场疲软，建议观望{market_detail}"
                        
            else:  # 市场中性
                if is_buy_signal:
                    return f"🟡 市场中性+买入信号，轻仓试探"
                elif is_sell_signal:
                    return f"🟡 市场中性+卖出信号，轻仓试探"
                else:
                    return f"➖ 市场中性，等待明确信号"
                    
        except Exception as e:
            self.logger.error(f"生成建议失败: {e}")
            return "⚠️ 建议生成错误"

    def run_analysis(self):
        """运行批量分析"""
        self.logger.info("🚀 开始批量期货趋势分析...")
        
        # 获取主力合约列表
        contracts_df = self.get_main_contracts()
        if contracts_df.empty:
            self.logger.error("无法获取主力合约列表，分析终止")
            return
        # print(contracts_df.head())
        
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
                time.sleep(random.uniform(1, 5))
            
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