import logging
from pybroker.data import DataSource 
import pandas as pd


class FuturesDataSource(DataSource):
    """期货数据源适配器"""
    
    def __init__(self, futures_data_manager, symbols=None):
        super().__init__()
        self.fdm = futures_data_manager
        self.logger = logging.getLogger('FuturesDataSource')
        self.symbols = symbols or []
        
    def _fetch_data(self, symbols, start_date, end_date, timeframe, adjust):
        """重写_fetch_data方法，从数据库获取期货数据"""
        all_data = []
        
        for symbol in symbols:
            try:
                # 从期货数据管理器获取数据
                data = self.fdm.query_data(
                    symbol=symbol, 
                    start_date=start_date, 
                    end_date=end_date
                )
                
                if data.empty:
                    print(f"未找到{symbol}的数据")
                    continue
                
                # 确保日期格式正确
                if 'date' in data.columns:
                    data['date'] = pd.to_datetime(data['date'])
                    data = data.sort_values('date')
                
                # 选择必需的列
                required_columns = ['symbol', 'date', 'open', 'high', 'low', 'close', 'volume']
                available_columns = [col for col in required_columns if col in data.columns]
                
                df_clean = data[available_columns].copy()
                df_clean = df_clean.dropna(subset=['open', 'high', 'low', 'close'])
                
                if not df_clean.empty:
                    all_data.append(df_clean)
                    print(f"加载{symbol}数据: {len(df_clean)}条记录")
                    
            except Exception as e:
                print(f"处理{symbol}数据时出错: {e}")
                continue
        
        if all_data:
            combined_data = pd.concat(all_data, ignore_index=True)
            combined_data = combined_data.sort_values(['symbol', 'date'])
            print(f"总共加载{len(combined_data)}条记录")
            return combined_data
        else:
            print("未加载到任何有效数据")
            return pd.DataFrame()
