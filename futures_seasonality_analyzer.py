import akshare as ak
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

plt.rcParams['font.sans-serif'] = ['SimHei']  # 用来正常显示中文标签
plt.rcParams['axes.unicode_minus'] = False    # 用来正常显示负号

class FuturesSeasonalityAnalyzer:
    def __init__(self, symbol="FG0"):
        self.symbol = symbol
        self.df = None
        
    def fetch_futures_data(self, years=10):
        """
        获取期货主力合约历史数据
        """
        print(f"正在获取{years}年的{self.symbol}期货主力合约数据...")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=years*365)
        
        try:
            # 获取主力合约数据
            df = ak.futures_main_sina(symbol=self.symbol)
            
            if df is None or df.empty:
                print("未获取到数据，请检查品种名称")
                return False
                
            # 重命名字段为英文
            column_mapping = {
                '日期': 'date',
                '开盘价': 'open', 
                '最高价': 'high',
                '最低价': 'low',
                '收盘价': 'close',
                '成交量': 'volume',
                '持仓量': 'open_interest',
                '动态结算价': 'settlement'
            }
            self.df = df.copy() 
            # 应用重命名
            self.df = self.df.rename(columns=column_mapping)
            
            # 数据预处理
            self.df['date'] = pd.to_datetime(self.df['date'])
            self.df = self.df.sort_values('date').reset_index(drop=True)
            
            # 筛选指定时间范围的数据
            self.df = self.df[self.df['date'] >= start_date]
            
            # 确保有足够的数据
            if len(self.df) < 252:  # 少于1年数据
                print("数据量不足，请检查数据获取情况")
                return False
                
            print(f"成功获取 {len(self.df)} 条数据，时间范围: {self.df['date'].min()} 到 {self.df['date'].max()}")
            print(f"数据字段: {list(self.df.columns)}")
            return True
            
        except Exception as e:
            print(f"数据获取失败: {e}")
            return False
    
    def calculate_seasonal_quantiles(self, column='close'):
        """
        计算季节性分位数
        """
        if self.df is None:
            print("请先获取数据")
            return None
        
        # 创建月份和日期的组合列，用于对齐不同年份的同一天
        seasonal_data = self.df.copy()
        seasonal_data['month_day'] = seasonal_data['date'].dt.strftime('%m-%d')
        
        # 按月份和日期分组计算分位数
        seasonal_stats = seasonal_data.groupby('month_day')[column].agg([
            ('count', 'count'),
            ('min', 'min'),
            ('q10', lambda x: x.quantile(0.10)),
            ('q25', lambda x: x.quantile(0.25)),
            ('median', 'median'),
            ('q75', lambda x: x.quantile(0.75)),
            ('q90', lambda x: x.quantile(0.90)),
            ('max', 'max'),
            ('mean', 'mean')
        ]).reset_index()
        
        return seasonal_stats
    
    def calculate_returns_seasonality(self):
        """
        计算收益率季节性分位数
        """
        if self.df is None:
            print("请先获取数据")
            return None
        
        # 计算日收益率
        returns_data = self.df.copy()
        returns_data['daily_return'] = returns_data['close'].pct_change()
        
        # 创建月份和日期的组合列
        returns_data['month_day'] = returns_data['date'].dt.strftime('%m-%d')
        
        # 按月份和日期分组计算收益率分位数
        returns_stats = returns_data.groupby('month_day')['daily_return'].agg([
            ('count', 'count'),
            ('min', 'min'),
            ('q10', lambda x: x.quantile(0.10)),
            ('q25', lambda x: x.quantile(0.25)),
            ('median', 'median'),
            ('q75', lambda x: x.quantile(0.75)),
            ('q90', lambda x: x.quantile(0.90)),
            ('max', 'max'),
            ('mean', 'mean'),
            ('positive_ratio', lambda x: (x > 0).mean()),
            ('volatility', lambda x: x.std())
        ]).reset_index()
        
        return returns_stats
    
    def calculate_open_interest_seasonality(self):
        """
        计算持仓量季节性分位数
        """
        if self.df is None or 'open_interest' not in self.df.columns:
            print("请先获取数据，或数据中不包含持仓量信息")
            return None
        
        # 创建月份和日期的组合列
        oi_data = self.df.copy()
        oi_data['month_day'] = oi_data['date'].dt.strftime('%m-%d')
        
        # 按月份和日期分组计算持仓量分位数
        oi_stats = oi_data.groupby('month_day')['open_interest'].agg([
            ('count', 'count'),
            ('min', 'min'),
            ('q10', lambda x: x.quantile(0.10)),
            ('q25', lambda x: x.quantile(0.25)),
            ('median', 'median'),
            ('q75', lambda x: x.quantile(0.75)),
            ('q90', lambda x: x.quantile(0.90)),
            ('max', 'max'),
            ('mean', 'mean')
        ]).reset_index()
        
        return oi_stats
    
    def calculate_comprehensive_seasonality(self):
        """
        计算综合季节性指标
        """
        if self.df is None:
            return None
            
        # 月度表现分析
        monthly_data = self.df.copy()
        monthly_data['year'] = monthly_data['date'].dt.year
        monthly_data['month'] = monthly_data['date'].dt.month
        
        monthly_returns = monthly_data.groupby(['year', 'month']).apply(
            lambda x: (x['close'].iloc[-1] - x['close'].iloc[0]) / x['close'].iloc[0]
        ).reset_index(name='monthly_return')
        
        # 月度统计
        monthly_stats = monthly_returns.groupby('month')['monthly_return'].agg([
            ('count', 'count'),
            ('mean_return', 'mean'),
            ('median_return', 'median'),
            ('std_return', 'std'),
            ('win_rate', lambda x: (x > 0).mean()),
            ('best_return', 'max'),
            ('worst_return', 'min')
        ]).reset_index()
        
        # 计算夏普比率（年化）
        monthly_stats['sharpe_ratio'] = (monthly_stats['mean_return'] * 12) / (monthly_stats['std_return'] * np.sqrt(12))
        
        return monthly_stats
    
    def plot_price_seasonality(self, seasonal_stats):
        """
        绘制价格季节性分位数图
        """
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 12))
        
        # 价格分位数通道图
        ax1.fill_between(range(len(seasonal_stats)), 
                        seasonal_stats['min'], 
                        seasonal_stats['max'], 
                        alpha=0.1, color='lightblue', label='Min-Max Range')
        
        ax1.fill_between(range(len(seasonal_stats)), 
                        seasonal_stats['q25'], 
                        seasonal_stats['q75'], 
                        alpha=0.3, color='blue', label='25%-75% Range')
        
        ax1.plot(seasonal_stats['median'], color='darkblue', linewidth=3, label='中位数')
        ax1.plot(seasonal_stats['mean'], color='red', linestyle='--', linewidth=2, label='平均值')
        
        # 标记当前年份的价格
        current_year = datetime.now().year
        current_data = self.df[self.df['date'].dt.year == current_year].copy()
        
        merged_data = seasonal_stats.copy()
        if not current_data.empty:
            current_data['month_day'] = current_data['date'].dt.strftime('%m-%d')
            
            # 合并当前数据到季节性统计数据中
            merged_data = pd.merge(seasonal_stats, current_data, on='month_day', how='left')
            
            # 检查合并后的列名
            current_price_col = 'close_y' if 'close_y' in merged_data.columns else 'close'
            if current_price_col in merged_data.columns:
                valid_current_data = merged_data[merged_data[current_price_col].notna()]
                if not valid_current_data.empty:
                    ax1.plot(valid_current_data[current_price_col], color='green', linewidth=2, 
                            label=f'{current_year}年价格', marker='o', markersize=3)
        
        ax1.set_title(f'{self.symbol}期货 - 价格季节性分位数通道', fontsize=16, fontweight='bold')
        ax1.set_ylabel('价格', fontsize=12)
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # 设置x轴刻度（每月标记）
        month_indices = []
        month_labels = []
        for i, month_day in enumerate(seasonal_stats['month_day']):
            month = int(month_day.split('-')[0])
            day = int(month_day.split('-')[1])
            if day == 1:  # 每月第一天
                month_indices.append(i)
                month_labels.append(f'{month}月')
        
        ax1.set_xticks(month_indices)
        ax1.set_xticklabels(month_labels, rotation=45)
        
        # 当前价格在历史分位数的位置
        if not current_data.empty and 'close_y' in merged_data.columns:
            valid_data = merged_data[merged_data['close_y'].notna()]
            if not valid_data.empty:
                positions = []
                for i, row in valid_data.iterrows():
                    current_price = row['close_y']
                    min_val = row['min']
                    max_val = row['max']
                    
                    if max_val > min_val:
                        position = (current_price - min_val) / (max_val - min_val)
                        positions.append(position)
                
                # 绘制分位数位置热图
                colors = ['red' if p > 0.7 else 'green' if p < 0.3 else 'yellow' for p in positions]
                ax2.bar(range(len(positions)), [p * 100 for p in positions], color=colors, alpha=0.7)
                
                # 添加水平参考线
                ax2.axhline(y=70, color='red', linestyle='--', alpha=0.5, label='高位 (70%)')
                ax2.axhline(y=30, color='green', linestyle='--', alpha=0.5, label='低位 (30%)')
                ax2.axhline(y=50, color='gray', linestyle='-', alpha=0.3, label='中位')
        
        ax2.set_title(f'{current_year}年价格在历史季节性通道中的位置 (%)', fontsize=14)
        ax2.set_xlabel('日期')
        ax2.set_ylabel('分位数位置 (%)')
        ax2.set_ylim(0, 100)
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        ax2.set_xticks(month_indices)
        ax2.set_xticklabels(month_labels, rotation=45)
        
        plt.tight_layout()
        plt.show()
        
        return merged_data
    
    def plot_returns_seasonality(self, returns_stats):
        """
        绘制收益率季节性分位数图
        """
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(16, 15))
        
        # 收益率分位数通道图
        ax1.fill_between(range(len(returns_stats)), 
                        returns_stats['q10'] * 100, 
                        returns_stats['q90'] * 100, 
                        alpha=0.1, color='lightcoral', label='10%-90% Range')
        
        ax1.fill_between(range(len(returns_stats)), 
                        returns_stats['q25'] * 100, 
                        returns_stats['q75'] * 100, 
                        alpha=0.3, color='red', label='25%-75% Range')
        
        ax1.plot(returns_stats['median'] * 100, color='darkred', linewidth=3, label='收益率中位数')
        ax1.plot(returns_stats['mean'] * 100, color='blue', linestyle='--', linewidth=2, label='收益率平均值')
        ax1.axhline(y=0, color='black', linestyle='-', alpha=0.5)
        
        ax1.set_title(f'{self.symbol}期货 - 日收益率季节性分位数通道 (%)', fontsize=16, fontweight='bold')
        ax1.set_ylabel('日收益率 (%)', fontsize=12)
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # 上涨概率图
        ax2.bar(range(len(returns_stats)), returns_stats['positive_ratio'] * 100, 
               alpha=0.7, color='green', label='历史上涨概率')
        ax2.axhline(y=50, color='red', linestyle='--', alpha=0.7, label='50%基准线')
        ax2.axhline(y=60, color='orange', linestyle=':', alpha=0.5, label='强势线 (60%)')
        ax2.axhline(y=40, color='orange', linestyle=':', alpha=0.5, label='弱势线 (40%)')
        
        ax2.set_title('历史季节性上涨概率 (%)', fontsize=14)
        ax2.set_ylabel('上涨概率 (%)', fontsize=12)
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        ax2.set_ylim(0, 100)
        
        # 波动率图
        ax3.bar(range(len(returns_stats)), returns_stats['volatility'] * 100, 
               alpha=0.7, color='purple', label='历史波动率')
        
        ax3.set_title('历史季节性波动率 (%)', fontsize=14)
        ax3.set_xlabel('日期')
        ax3.set_ylabel('波动率 (%)', fontsize=12)
        ax3.legend()
        ax3.grid(True, alpha=0.3)
        
        # 设置x轴刻度
        month_indices = []
        month_labels = []
        for i, month_day in enumerate(returns_stats['month_day']):
            month = int(month_day.split('-')[0])
            day = int(month_day.split('-')[1])
            if day == 1:
                month_indices.append(i)
                month_labels.append(f'{month}月')
        
        for ax in [ax1, ax2, ax3]:
            ax.set_xticks(month_indices)
            ax.set_xticklabels(month_labels, rotation=45)
        
        plt.tight_layout()
        plt.show()
        
        return returns_stats
    
    def plot_open_interest_seasonality2(self, oi_stats):
        """
        绘制持仓量季节性分位数图
        """
        if oi_stats is None:
            print("持仓量数据不可用")
            return None, []
            
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10))
        
        # 持仓量分位数通道图
        ax1.fill_between(range(len(oi_stats)), 
                        oi_stats['min'], 
                        oi_stats['max'], 
                        alpha=0.1, color='plum', label='Min-Max Range')
        
        ax1.fill_between(range(len(oi_stats)), 
                        oi_stats['q25'], 
                        oi_stats['q75'], 
                        alpha=0.3, color='purple', label='25%-75% Range')
        
        ax1.plot(oi_stats['median'], color='darkviolet', linewidth=3, label='持仓量中位数')
        ax1.plot(oi_stats['mean'], color='orange', linestyle='--', linewidth=2, label='持仓量平均值')
        
        # 标记当前年份的持仓量
        current_year = datetime.now().year
        current_data = self.df[self.df['date'].dt.year == current_year].copy()
        
        merged_oi = oi_stats.copy()
        positions = []
        
        if not current_data.empty:
            current_data['month_day'] = current_data['date'].dt.strftime('%m-%d')
            
            # 合并当前数据到季节性统计数据中
            merged_oi = pd.merge(oi_stats, current_data, on='month_day', how='left')
            
            # 检查合并后的列名
            current_oi_col = 'open_interest_y' if 'open_interest_y' in merged_oi.columns else 'open_interest'
            if current_oi_col in merged_oi.columns:
                valid_current_data = merged_oi[merged_oi[current_oi_col].notna()]
                if not valid_current_data.empty:
                    ax1.plot(valid_current_data[current_oi_col], color='green', linewidth=2, 
                            label=f'{current_year}年持仓量', marker='o', markersize=3)
        
        ax1.set_title(f'{self.symbol}期货 - 持仓量季节性分位数通道', fontsize=16, fontweight='bold')
        ax1.set_ylabel('持仓量', fontsize=12)
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # 设置x轴刻度（每月标记）
        month_indices = []
        month_labels = []
        for i, month_day in enumerate(oi_stats['month_day']):
            month = int(month_day.split('-')[0])
            day = int(month_day.split('-')[1])
            if day == 1:
                month_indices.append(i)
                month_labels.append(f'{month}月')
        
        ax1.set_xticks(month_indices)
        ax1.set_xticklabels(month_labels, rotation=45)
        
        # 当前持仓量在历史分位数的位置
        if not current_data.empty and 'open_interest_y' in merged_oi.columns:
            for i, row in merged_oi.iterrows():
                if not pd.isna(row['open_interest_y']):
                    current_oi = row['open_interest_y']
                    min_val = row['min']
                    max_val = row['max']
                    
                    if max_val > min_val:
                        position = (current_oi - min_val) / (max_val - min_val)
                        positions.append(position)
            
            if positions:
                # 绘制分位数位置热图
                colors = ['red' if p > 0.7 else 'green' if p < 0.3 else 'yellow' for p in positions]
                ax2.bar(range(len(positions)), [p * 100 for p in positions], color=colors, alpha=0.7)
        
        ax2.axhline(y=70, color='red', linestyle='--', alpha=0.5, label='高位 (70%)')
        ax2.axhline(y=30, color='green', linestyle='--', alpha=0.5, label='低位 (30%)')
        ax2.axhline(y=50, color='gray', linestyle='-', alpha=0.3, label='中位')
        
        ax2.set_title(f'{current_year}年持仓量在历史季节性通道中的位置 (%)', fontsize=14)
        ax2.set_xlabel('日期')
        ax2.set_ylabel('分位数位置 (%)')
        ax2.set_ylim(0, 100)
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        ax2.set_xticks(month_indices)
        ax2.set_xticklabels(month_labels, rotation=45)
        
        plt.tight_layout()
        plt.show()
        
        return merged_oi, positions
    
    def plot_open_interest_seasonality(self, oi_stats):
        """
        绘制持仓量季节性分位数图 - 修复位置显示问题
        """
        if oi_stats is None:
            print("持仓量数据不可用")
            return None, []
            
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 12))
        
        # 持仓量分位数通道图
        x_indices = range(len(oi_stats))
        
        ax1.fill_between(x_indices, 
                        oi_stats['min'], 
                        oi_stats['max'], 
                        alpha=0.1, color='plum', label='Min-Max Range')
        
        ax1.fill_between(x_indices, 
                        oi_stats['q25'], 
                        oi_stats['q75'], 
                        alpha=0.3, color='purple', label='25%-75% Range')
        
        ax1.plot(x_indices, oi_stats['median'], color='darkviolet', linewidth=3, label='持仓量中位数')
        ax1.plot(x_indices, oi_stats['mean'], color='orange', linestyle='--', linewidth=2, label='持仓量平均值')
        
        # 标记当前年份的持仓量
        current_year = datetime.now().year
        current_data = self.df[self.df['date'].dt.year == current_year].copy()
        
        merged_oi = oi_stats.copy()
        positions = []
        
        if not current_data.empty:
            current_data['month_day'] = current_data['date'].dt.strftime('%m-%d')
            
            # 合并当前数据到季节性统计数据中
            merged_oi = pd.merge(oi_stats, current_data, on='month_day', how='left')
            
            print(f"当前年份({current_year})持仓量数据点: {len(current_data)}个")
            
            # 使用正确的持仓量列
            current_oi_col = 'open_interest'
            if current_oi_col in merged_oi.columns:
                valid_indices = []
                valid_oi_values = []
                
                for i, row in merged_oi.iterrows():
                    if not pd.isna(row[current_oi_col]):
                        valid_indices.append(i)
                        valid_oi_values.append(row[current_oi_col])
                        
                        # 计算当前位置
                        current_oi = row[current_oi_col]
                        min_val = row['min']
                        max_val = row['max']
                        
                        if max_val > min_val and not pd.isna(current_oi):
                            position = (current_oi - min_val) / (max_val - min_val)
                            positions.append(position)
                        else:
                            positions.append(np.nan)
                    else:
                        positions.append(np.nan)
                
                # 绘制当前年份持仓量线
                if valid_indices:
                    ax1.plot(valid_indices, valid_oi_values, 
                            color='green', linewidth=2, 
                            label=f'{current_year}年持仓量', marker='o', markersize=3)
                    print(f"成功绘制{current_year}年持仓量线，包含{len(valid_indices)}个数据点")
        
        ax1.set_title(f'{self.symbol}期货 - 持仓量季节性分位数通道', fontsize=16, fontweight='bold')
        ax1.set_ylabel('持仓量', fontsize=12)
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # 设置x轴刻度（每月标记）
        month_indices = []
        month_labels = []
        for i, month_day in enumerate(oi_stats['month_day']):
            month = int(month_day.split('-')[0])
            day = int(month_day.split('-')[1])
            if day == 1:
                month_indices.append(i)
                month_labels.append(f'{month}月')
        
        ax1.set_xticks(month_indices)
        ax1.set_xticklabels(month_labels, rotation=45)
        
        # 当前持仓量在历史分位数的位置 - 使用线图替代柱状图
        valid_positions = [p for p in positions if not pd.isna(p)]
        if valid_positions:
            print(f"有效持仓量位置点: {len(valid_positions)}个")
            print(f"持仓量位置范围: {min(valid_positions):.3f} - {max(valid_positions):.3f}")
            
            # 创建对应的x轴索引
            position_indices = [i for i, p in enumerate(positions) if not pd.isna(p)]
            
            # 使用线图显示位置变化
            ax2.plot(position_indices, [p * 100 for p in valid_positions], 
                    color='red', linewidth=2, label='持仓量分位数位置', marker='o', markersize=2)
            
            # 填充不同区域的颜色
            ax2.fill_between(position_indices, 80, 100, alpha=0.3, color='red', label='极端高位 (>80%)')
            ax2.fill_between(position_indices, 70, 80, alpha=0.2, color='orange', label='高位 (70-80%)')
            ax2.fill_between(position_indices, 30, 70, alpha=0.1, color='yellow', label='中位 (30-70%)')
            ax2.fill_between(position_indices, 20, 30, alpha=0.2, color='lightgreen', label='低位 (20-30%)')
            ax2.fill_between(position_indices, 0, 20, alpha=0.3, color='green', label='极端低位 (<20%)')
            
            # 添加平均位置线
            avg_position = np.mean(valid_positions) * 100
            ax2.axhline(y=avg_position, color='blue', linestyle='-', linewidth=2, 
                    label=f'平均位置: {avg_position:.1f}%')
            
            # 标记关键位置点
            max_pos_idx = position_indices[np.argmax(valid_positions)]
            max_pos_val = max(valid_positions) * 100
            min_pos_idx = position_indices[np.argmin(valid_positions)]
            min_pos_val = min(valid_positions) * 100
            
            ax2.plot(max_pos_idx, max_pos_val, 'ro', markersize=8, label=f'最高位: {max_pos_val:.1f}%')
            ax2.plot(min_pos_idx, min_pos_val, 'go', markersize=8, label=f'最低位: {min_pos_val:.1f}%')
        
        # 添加水平参考线
        ax2.axhline(y=80, color='darkred', linestyle='--', alpha=0.7)
        ax2.axhline(y=70, color='red', linestyle='--', alpha=0.5)
        ax2.axhline(y=50, color='gray', linestyle='-', alpha=0.5)
        ax2.axhline(y=30, color='green', linestyle='--', alpha=0.5)
        ax2.axhline(y=20, color='darkgreen', linestyle='--', alpha=0.7)
        
        ax2.set_title(f'{current_year}年持仓量在历史季节性通道中的位置 (%)', fontsize=14)
        ax2.set_xlabel('日期')
        ax2.set_ylabel('分位数位置 (%)')
        ax2.set_ylim(0, 100)
        ax2.legend(loc='upper right', fontsize=9)
        ax2.grid(True, alpha=0.3)
        
        # 设置x轴刻度
        if valid_positions:
            display_indices = [i for i in month_indices if i <= max(position_indices)]
            display_labels = month_labels[:len(display_indices)]
            ax2.set_xticks(display_indices)
            ax2.set_xticklabels(display_labels, rotation=45)
        else:
            ax2.set_xticks(month_indices)
            ax2.set_xticklabels(month_labels, rotation=45)
        
        # 添加统计信息文本框
        if valid_positions:
            stats_text = f"""统计信息:
    平均位置: {np.mean(valid_positions):.1%}
    最高位置: {max(valid_positions):.1%}
    最低位置: {min(valid_positions):.1%}
    高位天数: {sum(1 for p in valid_positions if p > 0.7)}
    极端高位: {sum(1 for p in valid_positions if p > 0.8)}"""
            
            ax2.text(0.02, 0.98, stats_text, transform=ax2.transAxes, fontsize=10,
                    verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
        
        plt.tight_layout()
        plt.show()
        
        return merged_oi, positions
    
    def generate_comprehensive_report(self, seasonal_stats, returns_stats, monthly_stats, oi_stats, merged_data, merged_oi, oi_positions):
        """
        生成综合季节性分析报告
        """
        print("=" * 80)
        print(f"                   {self.symbol}期货季节性综合分析报告")
        print("=" * 80)
        
        # 数据概况
        print(f"\n📊 数据概况:")
        print(f"   数据期间: {self.df['date'].min().strftime('%Y-%m-%d')} 至 {self.df['date'].max().strftime('%Y-%m-%d')}")
        print(f"   总交易日: {len(self.df)} 天")
        print(f"   覆盖年份: {self.df['date'].dt.year.nunique()} 年")
        print(f"   最新价格: {self.df['close'].iloc[-1]:.2f}")
        
        # 计算年度表现
        yearly_returns = self.df.groupby(self.df['date'].dt.year).apply(
            lambda x: (x['close'].iloc[-1] - x['close'].iloc[0]) / x['close'].iloc[0] if len(x) > 0 else 0
        )
        positive_years = sum(yearly_returns > 0)
        yearly_win_rate = positive_years / len(yearly_returns) if len(yearly_returns) > 0 else 0
        
        print(f"   年度上涨概率: {yearly_win_rate:.1%} ({positive_years}/{len(yearly_returns)}年)")
        
        # 当前价格位置分析
        current_data = merged_data
        if 'close_y' in merged_data.columns:
            current_data = merged_data[merged_data['close_y'].notna()]
        
        price_positions = []
        if len(current_data) > 0:
            for _, row in current_data.iterrows():
                if 'close_y' in row and not pd.isna(row['close_y']) and row['max'] > row['min']:
                    position = (row['close_y'] - row['min']) / (row['max'] - row['min'])
                    price_positions.append(position)
            
            if price_positions:
                avg_position = np.mean(price_positions)
                position_level = "🔴 历史高位" if avg_position > 0.7 else "🟢 历史低位" if avg_position < 0.3 else "🟡 历史中位"
                
                print(f"\n📍 当前价格季节性位置:")
                print(f"   平均分位数: {avg_position:.1%} {position_level}")
                
                # 分析价格分布
                high_days = sum(1 for p in price_positions if p > 0.7)
                low_days = sum(1 for p in price_positions if p < 0.3)
                mid_days = len(price_positions) - high_days - low_days
                
                print(f"   位置分布: 高位{high_days}天, 中位{mid_days}天, 低位{low_days}天")
                
                # 近期趋势
                if len(price_positions) >= 10:
                    recent_trend = "上升" if price_positions[-1] > price_positions[-10] else "下降"
                    print(f"   近期趋势: {recent_trend}")
        
        # 月度表现排名
        print(f"\n🏆 月度表现排名:")
        
        # 最佳表现月份
        top_months = monthly_stats.nlargest(3, 'mean_return')[['month', 'mean_return', 'win_rate', 'std_return']]
        print(f"   💹 最佳表现月份:")
        for _, row in top_months.iterrows():
            month_name = f"{int(row['month'])}月"
            sharpe_info = f", 夏普{row['mean_return']/row['std_return']:.2f}" if row['std_return'] > 0 else ""
            print(f"      {month_name}: 收益率{row['mean_return']:.2%}, 胜率{row['win_rate']:.1%}{sharpe_info}")
        
        # 最差表现月份
        bottom_months = monthly_stats.nsmallest(3, 'mean_return')[['month', 'mean_return', 'win_rate', 'std_return']]
        print(f"   📉 最差表现月份:")
        for _, row in bottom_months.iterrows():
            month_name = f"{int(row['month'])}月"
            sharpe_info = f", 夏普{row['mean_return']/row['std_return']:.2f}" if row['std_return'] > 0 else ""
            print(f"      {month_name}: 收益率{row['mean_return']:.2%}, 胜率{row['win_rate']:.1%}{sharpe_info}")
        
        # 高胜率月份
        high_win_months = monthly_stats.nlargest(3, 'win_rate')[['month', 'mean_return', 'win_rate']]
        print(f"   🎯 高胜率月份:")
        for _, row in high_win_months.iterrows():
            month_name = f"{int(row['month'])}月"
            print(f"      {month_name}: 胜率{row['win_rate']:.1%}, 收益率{row['mean_return']:.2%}")
        
        # 季节性强度分析
        seasonal_strength = monthly_stats['mean_return'].std()
        volatility_avg = monthly_stats['std_return'].mean()
        
        print(f"\n📈 季节性特征强度:")
        print(f"   月度收益率标准差: {seasonal_strength:.4f}")
        strength_level = "强" if seasonal_strength > 0.02 else "中等" if seasonal_strength > 0.01 else "弱"
        print(f"   季节性强度: {strength_level}")
        print(f"   平均月度波动率: {volatility_avg:.2%}")
        
        # 当前月份分析
        current_month = datetime.now().month
        current_month_data = monthly_stats[monthly_stats['month'] == current_month]
        
        current_stats = None
        if not current_month_data.empty:
            current_stats = current_month_data.iloc[0]
            
            print(f"\n🔍 当前月份({current_month}月)深度分析:")
            print(f"   历史平均收益率: {current_stats['mean_return']:.2%}")
            print(f"   历史中位数收益率: {current_stats['median_return']:.2%}")
            print(f"   历史上涨概率: {current_stats['win_rate']:.1%}")
            print(f"   历史波动率: {current_stats['std_return']:.2%}")
            print(f"   最佳历史表现: {current_stats['best_return']:.2%}")
            print(f"   最差历史表现: {current_stats['worst_return']:.2%}")
            
            # 风险收益比
            if current_stats['std_return'] > 0:
                sharpe_ratio = current_stats['mean_return'] / current_stats['std_return']
                print(f"   风险收益比: {sharpe_ratio:.2f}")
            
            # 综合信号
            return_signal = "看涨" if current_stats['mean_return'] > 0 else "看跌"
            win_signal = "强势" if current_stats['win_rate'] > 0.6 else "弱势" if current_stats['win_rate'] < 0.4 else "中性"
            volatility_level = "高波动" if current_stats['std_return'] > 0.03 else "低波动"
            
            print(f"   💡 综合信号: {return_signal} | {win_signal} | {volatility_level}")
            
            # 历史数据可靠性
            data_years = current_stats['count']
            reliability = "高" if data_years >= 10 else "中等" if data_years >= 5 else "低"
            print(f"   数据可靠性: {reliability} (基于{data_years}年数据)")
        
        # 持仓量分析
        print(f"\n📊 持仓量季节性分析:")
        
        valid_positions = [p for p in oi_positions if not pd.isna(p)]
        if valid_positions:
            avg_position = np.mean(valid_positions)
            position_level = "🔴 历史高位" if avg_position > 0.7 else "🟢 历史低位" if avg_position < 0.3 else "🟡 历史中位"
            
            print(f"   持仓量平均分位数: {avg_position:.1%} {position_level}")
            print(f"   持仓量位置范围: {min(valid_positions):.1%} - {max(valid_positions):.1%}")
            
            # 分析分布情况
            extreme_high_count = sum(1 for p in valid_positions if p > 0.8)
            high_count = sum(1 for p in valid_positions if p > 0.7)
            low_count = sum(1 for p in valid_positions if p < 0.3)
            extreme_low_count = sum(1 for p in valid_positions if p < 0.2)
            
            print(f"   位置分布:")
            print(f"     ▪ 极端高位(>80%): {extreme_high_count}天")
            print(f"     ▪ 高位(>70%): {high_count}天") 
            print(f"     ▪ 中位(30%-70%): {len(valid_positions) - high_count - low_count}天")
            print(f"     ▪ 低位(<30%): {low_count}天")
            print(f"     ▪ 极端低位(<20%): {extreme_low_count}天")
            
            # 分析近期趋势
            if len(valid_positions) >= 10:
                recent_positions = valid_positions[-10:]
                trend = "📈 上升" if recent_positions[-1] > recent_positions[0] else "📉 下降"
                strength = abs(recent_positions[-1] - recent_positions[0])
                trend_strength = "强劲" if strength > 0.2 else "温和" if strength > 0.1 else "微弱"
                print(f"   近期趋势: {trend} ({trend_strength}, 变化{strength:.3f})")
            
            # 持仓量信号
            if avg_position > 0.8:
                print(f"   ⚠️  强烈信号: 持仓量持续处于极端高位，市场可能过热")
            elif avg_position > 0.7:
                print(f"   🔴 注意: 持仓量处于历史高位，需警惕风险")
            elif avg_position < 0.2:
                print(f"   ⚠️  强烈信号: 持仓量持续处于极端低位，可能存在机会")
            elif avg_position < 0.3:
                print(f"   🟢 机会: 持仓量处于历史低位，可能酝酿反弹")
        else:
            print("   ℹ️  当前年份持仓量数据不足或无法计算位置")
        
        # 收益率季节性特征
        print(f"\n📊 收益率季节性特征:")
        if returns_stats is not None:
            avg_daily_return = returns_stats['mean'].mean() * 100
            avg_positive_ratio = returns_stats['positive_ratio'].mean() * 100
            avg_volatility = returns_stats['volatility'].mean() * 100
            
            print(f"   平均日收益率: {avg_daily_return:.3f}%")
            print(f"   平均上涨概率: {avg_positive_ratio:.1f}%")
            print(f"   平均日波动率: {avg_volatility:.2f}%")
            
            # 寻找最佳交易时段
            best_periods = returns_stats.nlargest(3, 'positive_ratio')[['month_day', 'positive_ratio', 'mean']]
            if not best_periods.empty:
                print(f"   🎯 最佳交易时段:")
                for _, row in best_periods.iterrows():
                    print(f"      {row['month_day']}: 胜率{row['positive_ratio']:.1%}, 收益{row['mean']:.3%}")
        
        # 投资建议
        print(f"\n💎 季节性投资建议:")
        if current_stats is not None:
            # 基于多重因素的综合建议
            return_score = 2 if current_stats['mean_return'] > 0.005 else 1 if current_stats['mean_return'] > 0 else 0
            win_score = 2 if current_stats['win_rate'] > 0.6 else 1 if current_stats['win_rate'] > 0.5 else 0
            volatility_score = -1 if current_stats['std_return'] > 0.04 else 0
            
            # 考虑持仓量因素
            oi_score = 0
            if valid_positions:
                if avg_position > 0.8:
                    oi_score = -2  # 极端高位，强烈负面
                elif avg_position > 0.7:
                    oi_score = -1  # 高位，负面
                elif avg_position < 0.2:
                    oi_score = 2   # 极端低位，强烈正面
                elif avg_position < 0.3:
                    oi_score = 1   # 低位，正面
            
            total_score = return_score + win_score + volatility_score + oi_score
            
            if total_score >= 3:
                recommendation = "🟢 强烈看涨"
                reasoning = "历史表现优秀，季节性支撑强劲，多重指标向好"
            elif total_score >= 2:
                recommendation = "🔵 温和看涨" 
                reasoning = "季节性因素偏正面，整体表现稳定"
            elif total_score >= 1:
                recommendation = "🟡 中性"
                reasoning = "季节性信号不明显，多空因素交织"
            elif total_score >= 0:
                recommendation = "🟠 温和看跌"
                reasoning = "季节性因素偏负面，需谨慎操作"
            else:
                recommendation = "🔴 强烈看跌"
                reasoning = "历史表现疲弱，多重指标显示压力"
            
            print(f"   {recommendation} - {reasoning}")
            print(f"   综合评分: {total_score}分 (收益{return_score}, 胜率{win_score}, 波动{volatility_score}, 持仓量{oi_score})")
            
            # 具体操作建议
            print(f"\n   🎯 操作建议:")
            if current_stats['std_return'] > 0.03:
                print(f"      • 高波动环境，建议轻仓操作，设置宽止损")
            else:
                print(f"      • 波动率适中，可按正常仓位操作")
                
            if current_stats['win_rate'] > 0.6:
                print(f"      • 高胜率月份，适合趋势跟踪策略")
            elif current_stats['win_rate'] < 0.4:
                print(f"      • 低胜率月份，建议反转策略或观望")
            
            # 结合持仓量信号
            if valid_positions:
                if avg_position > 0.7:
                    print(f"      • 持仓量处于历史高位，注意回调风险")
                elif avg_position < 0.3:
                    print(f"      • 持仓量处于历史低位，可能存在反弹机会")
            
            # 结合价格位置
            if price_positions:
                price_avg_pos = np.mean(price_positions)
                if price_avg_pos > 0.7:
                    print(f"      • 价格处于季节性高位，追高风险较大")
                elif price_avg_pos < 0.3:
                    print(f"      • 价格处于季节性低位，安全边际较高")
        
        # 季节性策略总结
        print(f"\n📋 季节性策略总结:")
        best_months_str = ", ".join([f"{int(row['month'])}月" for _, row in top_months.iterrows()])
        worst_months_str = ", ".join([f"{int(row['month'])}月" for _, row in bottom_months.iterrows()])
        
        print(f"   1. 关注最佳月份: {best_months_str}")
        print(f"   2. 避开弱势月份: {worst_months_str}")
        
        current_signal = "正面" if total_score >= 2 else "中性" if total_score >= 1 else "负面"
        print(f"   3. 当前月份信号: {current_signal}")
        print(f"   4. 数据可靠性: {reliability if current_stats is not None else '中等'}")
        
        # 风险提示
        print(f"\n⚠️  风险提示:")
        print(f"   • 季节性分析基于历史数据，不代表未来表现")
        print(f"   • 实际交易需结合技术分析、基本面等因素")
        print(f"   • 投资有风险，入市需谨慎")
        
        print(f"\n" + "=" * 80)
        
    def plot_monthly_performance(self, monthly_stats):
        """
        绘制月度表现热图
        """
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))
        
        # 月度收益率热图
        monthly_returns = monthly_stats.set_index('month')['mean_return'] * 100
        colors = ['red' if x < 0 else 'green' for x in monthly_returns]
        bars1 = ax1.bar(monthly_stats['month'], monthly_returns, color=colors, alpha=0.7)
        
        # 添加数值标签
        for bar in bars1:
            height = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width()/2., height,
                    f'{height:.2f}%', ha='center', va='bottom' if height >= 0 else 'top')
        
        ax1.set_title(f'{self.symbol}期货 - 月度平均收益率 (%)', fontsize=16, fontweight='bold')
        ax1.set_ylabel('平均收益率 (%)', fontsize=12)
        ax1.grid(True, alpha=0.3)
        
        # 月度胜率热图
        win_rates = monthly_stats.set_index('month')['win_rate'] * 100
        colors2 = ['green' if x > 50 else 'red' for x in win_rates]
        bars2 = ax2.bar(monthly_stats['month'], win_rates, color=colors2, alpha=0.7)
        
        # 添加数值标签
        for bar in bars2:
            height = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width()/2., height,
                    f'{height:.1f}%', ha='center', va='bottom')
        
        ax2.axhline(y=50, color='red', linestyle='--', alpha=0.7, label='50%基准线')
        ax2.set_title('月度上涨概率 (%)', fontsize=14)
        ax2.set_xlabel('月份')
        ax2.set_ylabel('上涨概率 (%)', fontsize=12)
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        ax2.set_ylim(0, 100)
        
        plt.tight_layout()
        plt.show()
    
def analyze_futures_seasonality_comprehensive():
    """
    综合期货季节性分析
    """
    analyzer = FuturesSeasonalityAnalyzer(symbol="JM0")
    
    # 获取数据
    if not analyzer.fetch_futures_data(years=20):
        print("数据获取失败，程序退出")
        return
    
    # 计算各种季节性指标
    print("计算价格季节性分位数...")
    seasonal_stats = analyzer.calculate_seasonal_quantiles()
    
    print("计算收益率季节性分位数...")
    returns_stats = analyzer.calculate_returns_seasonality()
    
    print("计算月度综合表现...")
    monthly_stats = analyzer.calculate_comprehensive_seasonality()
    
    print("计算持仓量季节性分位数...")
    oi_stats = analyzer.calculate_open_interest_seasonality()
    
    # 绘制图表
    print("生成分析图表...")
    merged_data = analyzer.plot_price_seasonality(seasonal_stats)
    analyzer.plot_returns_seasonality(returns_stats)
    analyzer.plot_monthly_performance(monthly_stats)
    
    if oi_stats is not None:
        merged_oi, oi_positions = analyzer.plot_open_interest_seasonality(oi_stats)
    else:
        merged_oi, oi_positions = None, []
    
    # 生成综合报告
    analyzer.generate_comprehensive_report(seasonal_stats, returns_stats, monthly_stats, 
                                         oi_stats, merged_data, merged_oi, oi_positions)
    
    return analyzer, seasonal_stats, returns_stats, monthly_stats, oi_stats

# 执行综合分析
if __name__ == "__main__":
    analyzer, seasonal_stats, returns_stats, monthly_stats, oi_stats = analyze_futures_seasonality_comprehensive()