
from datetime import datetime
import logging
import sqlite3
from typing import Dict, List
import akshare as ak

import pandas as pd


class FuturesDataManager:
    '''
        用于添加、保存、更新期货数据
    '''
    
    def __init__(self, db_path: str = "E:\\db\\futures_data.db"):
        """
        初始化数据库管理器
        
        Args:
            db_path: SQLite数据库文件路径
        """
        self.db_path = db_path
        self.conn = None
        self.logger = logging.getLogger('FuturesDataManager')
        
        self._init_database()
        self._init_symbol_mapping()
    
    def _init_database(self):
        """初始化数据库表结构"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            cursor = self.conn.cursor()
            
            # 创建主力合约数据表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS futures_main_contracts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange TEXT,
                name TEXT,
                date TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                open_interest INTEGER,
                settlement_price REAL,
                data_type TEXT DEFAULT 'main_continuous',
                created_time TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_time TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, date)
            )
            ''')
            
            # 创建主力合约列表表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS main_contract_list (
                symbol TEXT PRIMARY KEY,
                exchange TEXT,
                name TEXT,
                is_active INTEGER DEFAULT 1,
                last_checked TEXT,
                created_time TEXT DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # 创建数据更新记录表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS data_update_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                last_update_date TEXT,
                data_count INTEGER,
                status TEXT,
                created_time TEXT DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            self.conn.commit()
            self.logger.info("数据库初始化完成")
            
        except Exception as e:
            self.logger.error(f"数据库初始化失败: {e}")
            if self.conn:
                self.conn.close()
                
    def _init_symbol_mapping(self):
        """初始化品种映射表"""
        self.exchange_mapping = {
            'dce': '大连商品交易所',
            'czce': '郑州商品交易所', 
            'shfe': '上海期货交易所',
            'cffex': '中国金融期货交易所'
        }
    
    def get_connection(self):
        """获取数据库连接"""
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path)
        return self.conn
    
    def get_current_main_contracts(self) -> pd.DataFrame:
        """
        获取当前所有主力合约列表
        
        Returns:
            pandas DataFrame with current main contracts
        """
        try:
            self.logger.info("正在获取当前主力合约列表...")
            main_contracts_df = ak.futures_display_main_sina()
            
            if main_contracts_df is None or main_contracts_df.empty:
                self.logger.warning("未获取到主力合约列表")
                return pd.DataFrame()
            
            self.logger.info(f"获取到{len(main_contracts_df)}个主力合约")
            return main_contracts_df
            
        except Exception as e:
            self.logger.error(f"获取主力合约列表失败: {e}")
            return pd.DataFrame()
    
    def update_main_contract_list(self):
        """
        更新主力合约列表到数据库
        """
        try:
            main_contracts = self.get_current_main_contracts()
            if main_contracts.empty:
                return False
            
            conn = self.get_connection()
            
            # 先标记所有合约为非活跃
            cursor = conn.cursor()
            cursor.execute("UPDATE main_contract_list SET is_active = 0")
            
            # 插入或更新当前主力合约
            for _, row in main_contracts.iterrows():
                cursor.execute('''
                INSERT OR REPLACE INTO main_contract_list 
                (symbol, exchange, name, is_active, last_checked)
                VALUES (?, ?, ?, 1, ?)
                ''', (row['symbol'], row['exchange'], row['name'], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            
            conn.commit()
            self.logger.info(f"已更新主力合约列表，共{len(main_contracts)}个合约")
            return True
            
        except Exception as e:
            self.logger.error(f"更新主力合约列表失败: {e}")
            return False
        
    def get_active_main_contracts(self) -> List[str]:
        """
        获取当前活跃的主力合约代码列表
        
        Returns:
            List of active main contract symbols
        """
        try:
            conn = self.get_connection()
            query = "SELECT symbol FROM main_contract_list WHERE is_active = 1"
            df = pd.read_sql_query(query, conn)
            return df['symbol'].tolist()
            
        except Exception as e:
            self.logger.error(f"获取活跃合约列表失败: {e}")
            return []
        
    def fetch_main_contract_data(self, symbol: str, start_date: str = "20100101", end_date: str = None) -> pd.DataFrame:
        """
        获取主力合约历史数据
        
        Args:
            symbol: 品种代码 (如 "M0", "RB0")
            start_date: 开始日期 "YYYYMMDD"
            end_date: 结束日期 "YYYYMMDD"，默认为今天
            
        Returns:
            pandas DataFrame
        """
        if end_date is None:
            end_date = datetime.now().strftime("%Y%m%d")
        
        try:
            self.logger.info(f"正在获取{symbol}主力合约历史数据...")
            
            # 使用akshare获取主力合约数据
            data = ak.futures_main_sina(symbol=symbol)
            if data is None or data.empty:
                self.logger.warning(f"未获取到{symbol}历史数据")
                return pd.DataFrame()
            
            # 重命名列
            data.rename(columns={
                '日期': 'date',
                '开盘价': 'open',
                '最高价': 'high', 
                '最低价': 'low',
                '收盘价': 'close',
                '成交量': 'volume',
                '持仓量': 'open_interest',
                '动态结算价': 'settlement_price'
            }, inplace=True)
            
            # 添加品种代码和交易所信息
            conn = self.get_connection()
            contract_info = pd.read_sql_query(
                f"SELECT symbol, exchange, name FROM main_contract_list WHERE symbol = '{symbol}'", 
                conn
            )
            
            if not contract_info.empty:
                data['symbol'] = contract_info['symbol'].iloc[0]
                data['exchange'] = contract_info['exchange'].iloc[0]
                data['name'] = contract_info['name'].iloc[0]
            else:
                data['symbol'] = symbol
                data['exchange'] = 'unknown'
                data['name'] = symbol
            
            data['data_type'] = 'main_continuous'
            
            # 过滤日期
            if start_date:
                data['date_dt'] = pd.to_datetime(data['date'])
                start_dt = datetime.strptime(start_date, "%Y%m%d")
                data = data[data['date_dt'] >= start_dt]
                data.drop('date_dt', axis=1, inplace=True)
            
            self.logger.info(f"成功获取{symbol}历史数据，共{len(data)}条记录")
            return data
            
        except Exception as e:
            self.logger.error(f"获取{symbol}历史数据失败: {e}")
            return pd.DataFrame()
    
    def save_to_database(self, data: pd.DataFrame, update_existing: bool = True):
        """
        保存数据到数据库，支持更新已有数据
        """
        if data is None or data.empty:
            self.logger.warning("无数据可保存")
            return False
        
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            inserted_count = 0
            updated_count = 0
            
            for i in range(min(3, len(data))):
                row = data.iloc[i]
                self.logger.info(f"第{i}行: symbol={row.get('symbol')}, date={row.get('date')}, "
                            f"open={row.get('open')}, close={row.get('close')}")
            
            for index, row in data.iterrows():
                symbol = row.get('symbol')
                date = row.get('date')
                
                # 调试每一行的处理
                self.logger.debug(f"处理: {symbol} {date}")
                
                # 检查该日期是否已存在数据
                cursor.execute(
                    'SELECT id FROM futures_main_contracts WHERE symbol = ? AND date = ?',
                    (symbol, date)
                )
                existing_record = cursor.fetchone()
                
                if existing_record:
                    self.logger.debug(f"记录已存在: {symbol} {date} (ID: {existing_record[0]})")
                    if update_existing:
                        # 更新现有记录
                        update_result = cursor.execute('''
                        UPDATE futures_main_contracts SET 
                            open = ?, high = ?, low = ?, close = ?, 
                            volume = ?, open_interest = ?, settlement_price = ?,
                            updated_time = CURRENT_TIMESTAMP
                        WHERE symbol = ? AND date = ?
                        ''', (
                            row.get('open'), row.get('high'), row.get('low'),
                            row.get('close'), row.get('volume'), 
                            row.get('open_interest'), row.get('settlement_price'),
                            symbol, date
                        ))
                        updated_count += 1
                        self.logger.debug(f"更新完成，影响行数: {cursor.rowcount}")
                else:
                    self.logger.debug(f"记录不存在，准备插入: {symbol} {date}")
                    # 插入新记录
                    try:
                        cursor.execute('''
                        INSERT INTO futures_main_contracts 
                        (symbol, exchange, name, date, open, high, low, close, volume, 
                        open_interest, settlement_price, data_type)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            symbol, row.get('exchange'), row.get('name'), 
                            date, row.get('open'), row.get('high'), 
                            row.get('low'), row.get('close'), row.get('volume'),
                            row.get('open_interest'), row.get('settlement_price'), 
                            row.get('data_type', 'main_continuous')
                        ))
                        inserted_count += 1
                        self.logger.debug(f"插入完成，影响行数: {cursor.rowcount}")
                    except Exception as insert_error:
                        self.logger.error(f"插入失败: {insert_error}")
                        self.logger.error(f"插入数据: symbol={symbol}, date={date}")
            
            # 在commit之前检查计数
            self.logger.info(f"准备提交: 插入{inserted_count}条, 更新{updated_count}条")
            
            conn.commit()
            self.logger.info(f"提交完成")
            
            # 验证实际影响的行数
            total_affected = inserted_count + updated_count
            self.logger.info(f"总影响行数: {total_affected}")
            
            # 记录更新日志
            if total_affected > 0:
                symbols = data['symbol'].unique()
                for symbol in symbols:
                    self._log_update(symbol, total_affected, 'success')
                
                self.logger.info(f"数据保存完成: 新增{inserted_count}条, 更新{updated_count}条")
            else:
                self.logger.warning("无新增或更新数据")
                    
            return True
            
        except Exception as e:
            self.logger.error(f"保存数据失败: {e}")
            import traceback
            self.logger.error(f"详细错误: {traceback.format_exc()}")
            if conn:
                conn.rollback()
            return False
        
    def _log_update(self, symbol: str, data_count: int, status: str = 'success'):
        """记录数据更新日志"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
            INSERT INTO data_update_log (symbol, last_update_date, data_count, status)
            VALUES (?, ?, ?, ?)
            ''', (symbol, datetime.now().strftime("%Y-%m-%d"), data_count, status))
            
            conn.commit()
        except Exception as e:
            self.logger.error(f"记录更新日志失败: {e}")
            
    def update_all_main_contracts_data(self, start_date: str = "20100101"):
        """
        更新所有主力合约的历史数据
        """
        # 先更新合约列表
        self.update_main_contract_list()
        
        # 获取活跃合约
        active_contracts = self.get_active_main_contracts()
        self.logger.info(f"开始更新{len(active_contracts)}个活跃合约的数据")
        
        total_records = 0
        for symbol in active_contracts:
            try:
                data = self.fetch_main_contract_data(symbol, start_date)
                if not data.empty:
                    success = self.save_to_database(data)
                    if success:
                        total_records += len(data)
                    self.logger.info(f"更新{symbol}完成，新增{len(data)}条记录")
                else:
                    self.logger.warning(f"{symbol}无新数据")
                
                # 避免请求过于频繁
                import time
                time.sleep(0.5)
                
            except Exception as e:
                self.logger.error(f"更新{symbol}时出错: {e}")
        
        self.logger.info(f"所有主力合约更新完成，共新增{total_records}条记录")
        return total_records
    
    def get_contract_info(self, symbol: str) -> Dict:
        """
        获取合约详细信息
        """
        try:
            conn = self.get_connection()
            query = "SELECT * FROM main_contract_list WHERE symbol = ?"
            df = pd.read_sql_query(query, conn, params=[symbol])
            if not df.empty:
                return df.iloc[0].to_dict()
            return {}
            
        except Exception as e:
            self.logger.error(f"获取合约信息失败: {e}")
            return {}
    
    def query_data(self, symbol: str = None, exchange: str = None, 
                  start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """
        查询数据库中的数据
        """
        try:
            conn = self.get_connection()
            
            query = "SELECT * FROM futures_main_contracts WHERE 1=1"
            params = []
            
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)
            
            if exchange:
                query += " AND exchange = ?"
                params.append(exchange)
            
            if start_date:
                query += " AND date >= ?"
                params.append(start_date)
            
            if end_date:
                query += " AND date <= ?"
                params.append(end_date)
            
            query += " ORDER BY date DESC"
            
            data = pd.read_sql_query(query, conn, params=params)
            self.logger.info(f"查询到{len(data)}条记录")
            return data
            
        except Exception as e:
            self.logger.error(f"查询数据失败: {e}")
            return pd.DataFrame()
    
    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            self.conn = None
            self.logger.info("数据库连接已关闭")