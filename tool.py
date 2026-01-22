

import base64
import hashlib
import hmac
import os
import time
from typing import Dict
import urllib
import pandas as pd
import requests
import json
import urllib.parse
from datetime import datetime
import numpy as np

from custom_indicators.three_moving_average import TripleMAStateTracker

# 1. 首先定义安全编码器（放在文件顶部）
class SafeDataEncoder(json.JSONEncoder):
    """终极安全编码器，处理各种常见类型"""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        # 添加其他可能需要处理的类型
        elif hasattr(obj, 'tolist'):  # 处理其他类似numpy的对象
            return obj.tolist()
        elif hasattr(obj, '__dict__'):  # 处理普通对象
            return obj.__dict__
        return super().default(obj)

# 2. 改进钉钉发送函数，增加自动转换
def send_custom_robot_group_message(access_token, secret, msg, at_user_ids=None, 
                                   at_mobiles=None, is_at_all=False, msg_type="markdown"):
    """
    增强版钉钉机器人消息发送
    :param msg_type: "text" 或 "markdown"，推荐使用 markdown 格式更美观
    """
    # 自动类型检测和转换
    original_msg = msg
    
    # 如果是字典，转换为安全的JSON字符串
    if isinstance(msg, dict):
        try:
            # 先尝试漂亮打印的JSON格式
            msg = json.dumps(msg, cls=SafeDataEncoder, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"JSON序列化失败，使用字符串回退: {e}")
            msg = str(msg)
    # 如果是其他非字符串类型，也转换为字符串
    elif not isinstance(msg, str):
        msg = str(msg)
    
    # 计算签名（原有逻辑保持不变）
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f'{timestamp}\n{secret}'
    hmac_code = hmac.new(
        secret.encode('utf-8'), 
        string_to_sign.encode('utf-8'), 
        digestmod=hashlib.sha256
    ).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    
    url = f'https://oapi.dingtalk.com/robot/send?access_token={access_token}&timestamp={timestamp}&sign={sign}'
    
    # 构建消息体，支持 text 和 markdown 格式
    body = {
        "at": {
            "isAtAll": str(is_at_all).lower(),
            "atUserIds": at_user_ids or [],
            "atMobiles": at_mobiles or []
        },
        "msgtype": msg_type
    }
    
    if msg_type == "markdown":
        # 根据原始消息类型设置不同的标题
        title = "交易信号" if isinstance(original_msg, dict) else "系统通知"
        body["markdown"] = {
            "title": title,
            "text": msg if isinstance(msg, str) else str(msg)
        }
    else:  # text 类型
        body["text"] = {
            "content": msg if isinstance(msg, str) else str(msg)
        }
    
    headers = {'Content-Type': 'application/json'}
    
    try:
        resp = requests.post(url, json=body, headers=headers, timeout=10)
        resp.raise_for_status()  # 检查HTTP错误
        result = resp.json()
        print(f"钉钉消息发送成功: {result.get('errmsg', 'Unknown')}")
        return result
    except requests.exceptions.RequestException as e:
        print(f"钉钉消息发送失败: {e}")
        return {"errcode": -1, "errmsg": str(e)}
    
def send_swing_signal_to_dingding(signal):
        # 创建完整的Markdown消息
    markdown_msg = format_swing_signal_as_markdown(
        signal_dict=signal
    )
    
    # 发送到钉钉
    send_custom_robot_group_message(
        access_token="c1bd4f9c9f3fd282c322e5c8dcbb04431ab5b7748b318120e3f5b578e28d21f1",
        secret="SEC4e8ba1375cc55c628922fe1daf9a9e7c75d26cefd1fc389eaad1989f6990d3b4",
        msg=markdown_msg,
        is_at_all=True,
        msg_type="markdown"
    )

def send_to_dingding(signal, symbol=None, symbol_to_name_dict=None):
    '''
    发送交易信号到钉钉群（完整信息版）
    :param signal: 交易信号字典
    :param symbol: 合约代码（如 IF2406）
    :param symbol_to_name_dict: 合约代码到名称的映射字典
    '''
    # 创建完整的Markdown消息
    markdown_msg = format_signal_as_markdown(
        signal_dict=signal,
        symbol=symbol,
        symbol_to_name_dict=symbol_to_name_dict
    )
    
    # 发送到钉钉
    send_custom_robot_group_message(
        access_token="c1bd4f9c9f3fd282c322e5c8dcbb04431ab5b7748b318120e3f5b578e28d21f1",
        secret="SEC4e8ba1375cc55c628922fe1daf9a9e7c75d26cefd1fc389eaad1989f6990d3b4",
        msg=markdown_msg,
        is_at_all=True,
        msg_type="markdown"
    )
    
def send_markdown_to_dingding(msg):
    '''
        发送markdown消息到钉钉上面去
    '''
    send_custom_robot_group_message(
        access_token="c1bd4f9c9f3fd282c322e5c8dcbb04431ab5b7748b318120e3f5b578e28d21f1",
        secret="SEC4e8ba1375cc55c628922fe1daf9a9e7c75d26cefd1fc389eaad1989f6990d3b4",
        msg=msg,
        is_at_all=True,
        msg_type="markdown"
    )

def evaluate_force_index_general(force_index, price, signal_type):
    """
    通用力度指数评估函数（适合所有合约）
    
    参数：
        force_index: 原始力度指数值
        price: 当前价格
        signal_type: 'LONG' 或 'SHORT'
        
    返回：
        (adjusted_score, description)
    """
    
    if price <= 0:
        return 0, "价格无效，无法评估力度"
    
    # 计算相对力度百分比
    force_percent = (force_index / price) * 100
    
    # 为每种信号类型定义评估逻辑
    if signal_type == 'LONG':
        return _evaluate_long_force(force_percent)
    elif signal_type == 'SHORT':
        return _evaluate_short_force(force_percent)
    else:
        return 0, "信号类型无效"
    
def _evaluate_long_force(force_percent):
    """评估做多信号的力度"""
    
    # 做多：负向力度（force_percent < 0）是机会
    if force_percent < -5.0:  # 极端负向
        return 3.0, f"🔥 力度极端负向({force_percent:.2f}%)，强烈做多信号"
    elif force_percent < -2.0:  # 非常负向
        return 2.5, f"✅ 力度非常负向({force_percent:.2f}%)，优秀做多信号"
    elif force_percent < -1.0:  # 负向
        return 2.0, f"✅ 力度负向({force_percent:.2f}%)，良好做多机会"
    elif force_percent < -0.5:  # 轻微负向
        return 1.5, f"⚠️ 力度轻微负向({force_percent:.2f}%)，可做多"
    elif force_percent < -0.2:  # 微弱负向
        return 1.0, f"⚠️ 力度微弱负向({force_percent:.2f}%)，勉强可做多"
    elif force_percent < -0.05:  # 极微弱负向
        return 0.5, f"➖ 力度极微弱负向({force_percent:.2f}%)，谨慎做多"
    elif force_percent <= 0.05 and force_percent >= -0.05:  # 中性
        return 0, f"➖ 力度中性({force_percent:.2f}%)"
    elif force_percent > 5.0:  # 极端正向
        return -3.0, f"❌ 力度极端正向({force_percent:.2f}%)，严重不适合做多"
    elif force_percent > 2.0:  # 非常正向
        return -2.5, f"❌ 力度非常正向({force_percent:.2f}%)，不适合做多"
    elif force_percent > 1.0:  # 正向
        return -2.0, f"❌ 力度正向({force_percent:.2f}%)，不建议做多"
    elif force_percent > 0.5:  # 轻微正向
        return -1.5, f"⚠️ 力度轻微正向({force_percent:.2f}%)，谨慎做多"
    elif force_percent > 0.2:  # 微弱正向
        return -1.0, f"⚠️ 力度微弱正向({force_percent:.2f}%)，不推荐做多"
    else:  # 0.05% - 0.2%
        return -0.5, f"➖ 力度极微弱正向({force_percent:.2f}%)，勉强可做多"


def _evaluate_short_force(force_percent):
    """评估做空信号的力度"""
    
    # 做空：正向力度（force_percent > 0）是机会
    if force_percent > 5.0:  # 极端正向
        return 3.0, f"🔥 力度极端正向({force_percent:.2f}%)，强烈做空信号"
    elif force_percent > 2.0:  # 非常正向
        return 2.5, f"✅ 力度非常正向({force_percent:.2f}%)，优秀做空信号"
    elif force_percent > 1.0:  # 正向
        return 2.0, f"✅ 力度正向({force_percent:.2f}%)，良好做空机会"
    elif force_percent > 0.5:  # 轻微正向
        return 1.5, f"⚠️ 力度轻微正向({force_percent:.2f}%)，可做空"
    elif force_percent > 0.2:  # 微弱正向
        return 1.0, f"⚠️ 力度微弱正向({force_percent:.2f}%)，勉强可做空"
    elif force_percent > 0.05:  # 极微弱正向
        return 0.5, f"➖ 力度极微弱正向({force_percent:.2f}%)，谨慎做空"
    elif force_percent <= 0.05 and force_percent >= -0.05:  # 中性
        return 0, f"➖ 力度中性({force_percent:.2f}%)"
    elif force_percent < -5.0:  # 极端负向
        return -3.0, f"❌ 力度极端负向({force_percent:.2f}%)，严重不适合做空"
    elif force_percent < -2.0:  # 非常负向
        return -2.5, f"❌ 力度非常负向({force_percent:.2f}%)，不适合做空"
    elif force_percent < -1.0:  # 负向
        return -2.0, f"❌ 力度负向({force_percent:.2f}%)，不建议做空"
    elif force_percent < -0.5:  # 轻微负向
        return -1.5, f"⚠️ 力度轻微负向({force_percent:.2f}%)，谨慎做空"
    elif force_percent < -0.2:  # 微弱负向
        return -1.0, f"⚠️ 力度微弱负向({force_percent:.2f}%)，不推荐做空"
    else:  # -0.05% - -0.2%
        return -0.5, f"➖ 力度极微弱负向({force_percent:.2f}%)，勉强可做空"


def get_contract_data(csv_path: str, target_symbol: str) -> Dict:
    """
    读取CSV文件，获取具体合约及其主力合约的数据
    
    参数：
        csv_path: CSV文件路径
        target_symbol: 目标合约代码，如"RB2605"
    
    返回：
        Dict: 包含目标合约和主力合约数据的字典
    """
    try:
        # 检查文件是否存在
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"CSV文件不存在: {csv_path}")
        
        # 读取CSV文件
        df = pd.read_csv(csv_path)
        
        # 检查必要列
        required_columns = ['symbol', 'symbol_name', 'close_price', 'trend_text', 
                           'market_strength', 'buy_signal', 'sell_signal', 'signal_strength']
        
        missing_cols = [col for col in required_columns if col not in df.columns]
        if missing_cols:
            raise ValueError(f"CSV文件缺少必要列: {missing_cols}")
        
        # 提取品种代码（如RB2605 -> RB）
        product_code = ''.join([c for c in target_symbol if c.isalpha()])
        if not product_code:
            raise ValueError(f"无法从合约代码 {target_symbol} 中提取品种代码")
        
        # 构建主力合约代码（如RB -> RB0）
        main_contract_symbol = f"{product_code}0"
        
        # 查找目标合约和主力合约
        main_data = df[df['symbol'] == main_contract_symbol]
        if main_data.empty:
            raise ValueError(f"未找到主力合约: {main_contract_symbol}")
        
        # 获取数据
        main_row = main_data.iloc[0]
        
        # 格式化输出
        result = {
            'success': True,
            'main_contract': {
                'symbol': main_row['symbol'],
                'symbol_name': main_row['symbol_name'],
                'close_price': main_row['close_price'],
                'trend_text': main_row['trend_text'],
                'market_strength': main_row['market_strength'],
                'buy_signal': int(main_row['buy_signal']),
                'sell_signal': int(main_row['sell_signal']),
                'signal_strength': main_row['signal_strength'],
                'rsi': main_row.get('rsi', 50),
                'atr_percent': main_row.get('atr_percent', '0.0%'),
                'volume_change_pct': main_row.get('volume_change_pct', 0),
                'oi_change_pct': main_row.get('oi_change_pct', 0),
                'analysis_time': main_row.get('analysis_time', '')
            }
        }
        
        return result
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }

def format_swing_signal_as_markdown(signal_dict):
    """将交易信号格式化为钉钉Markdown消息（带信号质量评估）"""
    # 处理时间戳
    timestamp = signal_dict.get('timestamp')
    if isinstance(timestamp, datetime):
        time_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
    else:
        time_str = str(timestamp)
    
    # 获取合约名称
    symbol = signal_dict.get('symbol')
    symbol_name = signal_dict.get('symbol_name')
    
    # 信号类型颜色标识
    signal_type = signal_dict.get('signal_type', 'UNKNOWN')
    if signal_type == 'LONG':
        signal_display = '🟢 做多 LONG'
        action_text = '考虑做多'
    elif signal_type == 'SHORT':
        signal_display = '🔴 做空 SHORT'
        action_text = '考虑做空'
    else:
        signal_display = f'⚪ {signal_type}'
        action_text = '保持观望'
    
    # 趋势方向判断
    state_change = signal_dict.get('trend', 0)
    if state_change == TripleMAStateTracker.CONSOL_TO_UPTREND:
        trend_display = '📈 自横盘转上涨'
    elif state_change == TripleMAStateTracker.CONSOL_TO_DOWNTREND:
        trend_display = '📈 自横盘转下跌'
    elif state_change == TripleMAStateTracker.UPTREND_TO_CONSOL:
        trend_display = '📈 自上涨转横盘 '
    elif state_change == TripleMAStateTracker.DOWNTREND_TO_CONSOL:
        trend_display = '📈 自下跌转横盘 '
    else:
        trend_display = '📈 无趋势 '
    
    # ========== 新增：信号质量评估 ==========
    quality_score, quality_details, quality_level, quality_text = evaluate_signal_quality(signal_dict)
    recommendation = get_trading_recommendation(quality_score, signal_type)
    
    # ========== 计算止损点数 ==========
    atr = float(signal_dict.get('atr', 0))
    stop_loss_points = int(round(atr * 2))  # 2倍ATR，取整数
    trend_is_stable = float(signal_dict.get('trend_is_stable', False))
    trend_is_stable_text = "稳定" if trend_is_stable else "不稳定"
    trend_strength = int(signal_dict.get('trend_strength', 0))
    
    # ========== 根据信号类型显示交易建议 ==========
    trading_suggestion_text = ""
    if signal_type == 'LONG':
        suggested_price = float(signal_dict.get('suggested_buy_long', 0))
        distance = float(signal_dict.get('distance_to_buy', 0))
        trading_suggestion_text = f"""#### 🎮 交易建议
- **当前价格**：`{signal_dict.get('price', 0):.2f}`
- **5分钟入场价**：`{signal_dict.get('enter_donchian_up', 0)}`
- **均线穿透入场**：`{suggested_price:.2f}`
- **向上突破价位**：`{signal_dict.get('donchian_up', 0)}`
- **距做多点**：`{distance:.2f}`
- **止损点数**：`{stop_loss_points}`
- **力度指数**：`{signal_dict.get('force_index', 0):.2f}`
"""
    elif signal_type == 'SHORT':
        suggested_price = float(signal_dict.get('suggested_sell_short', 0))
        distance = float(signal_dict.get('distance_to_sell', 0))
        trading_suggestion_text = f"""#### 🎮 交易建议
- **当前价格**：`{signal_dict.get('price', 0):.2f}`
- **5分钟入场价**：`{signal_dict.get('enter_donchian_down', 0)}`
- **均线穿透入场**：`{suggested_price:.2f}`
- **突破价位**：`{signal_dict.get('donchian_down', 0)}`
- **距做空点**：`{distance:.2f}`
- **止损点数**：`{stop_loss_points}`
- **力度指数**：`{signal_dict.get('force_index', 0):.2f}`
"""
    else:
        # 如果是观望信号，显示所有信息
        suggested_buy_long = float(signal_dict.get('suggested_buy_long', 0))
        distance_to_buy = float(signal_dict.get('distance_to_buy', 0))
        suggested_sell_short = float(signal_dict.get('suggested_sell_short', 0))
        distance_to_sell = float(signal_dict.get('distance_to_sell', 0))
        trading_suggestion_text = f"""#### 🎮 交易建议
- **当前价格**：`{signal_dict.get('price', 0):.2f}`
- **做多入场**：`{suggested_buy_long:.2f}`
- **距做多点**：`{distance_to_buy:.2f}`
- **做空入场**：`{suggested_sell_short:.2f}`
- **距做空点**：`{distance_to_sell:.2f}`
- **止损点数**：`{stop_loss_points}`
- **力度指数**：`{signal_dict.get('force_index', 0):.2f}`
"""
    
    # 获取主力合约数据
    result = get_contract_data(csv_path="./reports/lastest_trend_analysis.csv", target_symbol=symbol)
    main_contract_info = None
    if result["success"]:
        main_contract_info = f"{result['main_contract']['symbol']}|{result['main_contract']['trend_text']}|{result['main_contract']['market_strength']}"
    
    # ========== 构建Markdown消息 ==========
    markdown_text = f"""### 🚀 30分钟波段期货交易信号

**{signal_display}** | **{action_text}**

---

#### 📋 合约信息
- **合约名称**：{symbol_name if symbol_name else '未知'}
- **合约代码**：`{symbol if symbol else 'N/A'}`
- **信号时间**：{time_str}
- **信号质量**：{quality_level} **{quality_score}/10** ({quality_text})
- **信号**：`{trend_display}`
- **信号强度**：{trend_strength}
- **信号是否稳定**：`{trend_is_stable_text}`
- **大趋势**：{main_contract_info}

{trading_suggestion_text}

### 💡 操作建议
- {recommendation['icon']} **{recommendation['action']}**
- 📊 **建议仓位**：{recommendation['position_size']}
- ⚠️ **风险等级**：{recommendation['risk_level']}
- 💡 **策略建议**：{recommendation['suggestion']}

#### 🎯 技术指标
- **均线指标**：EMA快线=`{signal_dict.get('ema_fast', 0):.2f}` | EMA慢线=`{signal_dict.get('ema_slow', 0):.2f}`
- **动量指标**：RSI=`{signal_dict.get('rsi', 0):.2f}` | 力度指数=`{signal_dict.get('force_index', 0):.2f}` | ATR=`{signal_dict.get('atr', 0):.2f}`
- **价值通道**：上通道=`{signal_dict.get('value_up_channel', 0):.2f}` | 下通道=`{signal_dict.get('value_down_channel', 0):.2f}` | 大小=`{signal_dict.get('value_size', 0)}`
- **突破通道**：上轨=`{signal_dict.get('donchian_up', 0)}` | 中轨=`{signal_dict.get('donchian_mid', 0)}` | 下轨=`{signal_dict.get('donchian_down', 0)}` | 大小=`{signal_dict.get('donchian_channel_size', 0)}`

#### 🏆 信号质量评估
**评估详情：**
"""
    # 添加评估详情
    for detail in quality_details:
        markdown_text += f"- {detail}\n"
    
    # 添加风险提示
    markdown_text += f"""
---

> ⚠️ **信号选择**：信号质量大于5以上的信号为佳
> 📊 **入场提示**：建议在1分钟或5分钟周期趋势向上时进场 \n
> 🛡️ **止损保护**：建议严格执行`{stop_loss_points}`点止损
"""
    
    return markdown_text

def format_signal_as_markdown(signal_dict, symbol=None, symbol_to_name_dict=None):
    """将交易信号格式化为钉钉Markdown消息（带信号质量评估）"""
    # 处理时间戳
    timestamp = signal_dict.get('timestamp')
    if isinstance(timestamp, datetime):
        time_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
    else:
        time_str = str(timestamp)
    
    # 获取合约名称
    symbol_name = None
    if symbol and symbol_to_name_dict:
        symbol_name = symbol_to_name_dict.get(symbol)
    
    # 信号类型颜色标识
    signal_type = signal_dict.get('signal_type', 'UNKNOWN')
    if signal_type == 'LONG':
        signal_display = '🟢 做多 LONG'
        action_text = '考虑做多'
    elif signal_type == 'SHORT':
        signal_display = '🔴 做空 SHORT'
        action_text = '考虑做空'
    else:
        signal_display = f'⚪ {signal_type}'
        action_text = '保持观望'
    
    # 趋势方向判断
    state_change = signal_dict.get('trend', 0)
    if state_change == TripleMAStateTracker.CONSOL_TO_UPTREND:
        trend_display = '📈 自横盘转上涨'
    elif state_change == TripleMAStateTracker.CONSOL_TO_DOWNTREND:
        trend_display = '📈 自横盘转下跌'
    elif state_change == TripleMAStateTracker.UPTREND_TO_CONSOL:
        trend_display = '📈 自上涨转横盘 '
    elif state_change == TripleMAStateTracker.DOWNTREND_TO_CONSOL:
        trend_display = '📈 自下跌转横盘 '
    else:
        trend_display = '📈 无趋势 '

    
    # ========== 新增：信号质量评估 ==========
    quality_score, quality_details, quality_level, quality_text = evaluate_signal_quality(signal_dict)
    recommendation = get_trading_recommendation(quality_score, signal_type)
    
    # ========== 计算止损点数 ==========
    atr = float(signal_dict.get('atr', 0))
    stop_loss_points = int(round(atr * 2))  # 2倍ATR，取整数
    trend_is_stable = float(signal_dict.get('trend_is_stable', False))
    trend_is_stable_text = "稳定" if trend_is_stable else "不稳定"
    trend_strength = int(signal_dict.get('trend_strength', 0))
    
    # ========== 根据信号类型显示交易建议 ==========
    trading_suggestion_text = ""
    if signal_type == 'LONG':
        suggested_price = float(signal_dict.get('suggested_buy_long', 0))
        distance = float(signal_dict.get('distance_to_buy', 0))
        trading_suggestion_text = f"""#### 🎮 交易建议
- **当前价格**：`{signal_dict.get('price', 0):.2f}`
- **1分钟入场价**：`{signal_dict.get('enter_donchian_up', 0)}`
- **均线穿透入场**：`{suggested_price:.2f}`
- **向上突破价位**：`{signal_dict.get('donchian_up', 0)}`
- **距做多点**：`{distance:.2f}`
- **止损点数**：`{stop_loss_points}`
- **力度指数**：`{signal_dict.get('force_index', 0):.2f}`
"""
    elif signal_type == 'SHORT':
        suggested_price = float(signal_dict.get('suggested_sell_short', 0))
        distance = float(signal_dict.get('distance_to_sell', 0))
        trading_suggestion_text = f"""#### 🎮 交易建议
- **当前价格**：`{signal_dict.get('price', 0):.2f}`
- **1分钟入场价**：`{signal_dict.get('enter_donchian_down', 0)}`
- **均线穿透入场**：`{suggested_price:.2f}`
- **突破价位**：`{signal_dict.get('donchian_down', 0)}`
- **距做空点**：`{distance:.2f}`
- **止损点数**：`{stop_loss_points}`
- **力度指数**：`{signal_dict.get('force_index', 0):.2f}`
"""
    else:
        # 如果是观望信号，显示所有信息
        suggested_buy_long = float(signal_dict.get('suggested_buy_long', 0))
        distance_to_buy = float(signal_dict.get('distance_to_buy', 0))
        suggested_sell_short = float(signal_dict.get('suggested_sell_short', 0))
        distance_to_sell = float(signal_dict.get('distance_to_sell', 0))
        trading_suggestion_text = f"""#### 🎮 交易建议
- **当前价格**：`{signal_dict.get('price', 0):.2f}`
- **做多入场**：`{suggested_buy_long:.2f}`
- **距做多点**：`{distance_to_buy:.2f}`
- **做空入场**：`{suggested_sell_short:.2f}`
- **距做空点**：`{distance_to_sell:.2f}`
- **止损点数**：`{stop_loss_points}`
- **力度指数**：`{signal_dict.get('force_index', 0):.2f}`
"""
    
    # 获取主力合约数据
    result = get_contract_data(csv_path="./reports/lastest_trend_analysis.csv", target_symbol=symbol)
    main_contract_info = None
    if result["success"]:
        main_contract_info = f"{result['main_contract']['symbol']}|{result['main_contract']['trend_text']}|{result['main_contract']['market_strength']}"
    
    # ========== 构建Markdown消息 ==========
    markdown_text = f"""### 🚀 期货交易15分钟周期信号

**{signal_display}** | **{action_text}**

---
#### 📋 合约信息
- **合约名称**：{symbol_name if symbol_name else '未知'}
- **合约代码**：`{symbol if symbol else 'N/A'}`
- **信号时间**：{time_str}
- **信号质量**：{quality_level} **{quality_score}/10** ({quality_text})
- **信号**：`{trend_display}`
- **信号是否稳定**：`{trend_is_stable_text}`
- **信号强度**：{trend_strength}
- **大趋势**：{main_contract_info}

{trading_suggestion_text}

### 💡 操作建议
- {recommendation['icon']} **{recommendation['action']}**
- 📊 **建议仓位**：{recommendation['position_size']}
- ⚠️ **风险等级**：{recommendation['risk_level']}
- 💡 **策略建议**：{recommendation['suggestion']}

#### 🎯 技术指标
- **均线指标**：EMA快线=`{signal_dict.get('ema_fast', 0):.2f}` | EMA慢线=`{signal_dict.get('ema_slow', 0):.2f}`
- **动量指标**：RSI=`{signal_dict.get('rsi', 0):.2f}` | 力度指数=`{signal_dict.get('force_index', 0):.2f}` | ATR=`{signal_dict.get('atr', 0):.2f}`
- **价值通道**：上通道=`{signal_dict.get('value_up_channel', 0):.2f}` | 下通道=`{signal_dict.get('value_down_channel', 0):.2f}` | 大小=`{signal_dict.get('value_size', 0)}`
- **突破通道**：上轨=`{signal_dict.get('donchian_up', 0)}` | 中轨=`{signal_dict.get('donchian_mid', 0)}` | 下轨=`{signal_dict.get('donchian_down', 0)}` | 大小=`{signal_dict.get('donchian_channel_size', 0)}`

#### 🏆 信号质量评估
**评估详情：**
"""
    # 添加评估详情
    for detail in quality_details:
        markdown_text += f"- {detail}\n"
    
    # 添加风险提示
    markdown_text += f"""
---

> ⚠️ **信号选择**：信号质量大于5以上的信号为佳
> 📊 **入场提示**：建议在1分钟或5分钟周期趋势向上时进场
> 🛡️ **止损保护**：建议严格执行`{stop_loss_points}`点止损
"""
    
    return markdown_text

def evaluate_signal_quality(signal_dict):
    """评估信号质量（0-10分）
    
    参数：
        signal_dict: 包含信号信息的字典
        
    返回：
        tuple: (quality_score, quality_details, quality_level, quality_text)
        其中：
        - quality_score: 质量评分（0-10）
        - quality_details: 评估详情列表
        - quality_level: 质量等级图标
        - quality_text: 质量等级文本
    """
    score = 5.0  # 基础分
    details = []
    
    # 获取所有必要的信号参数
    signal_type = signal_dict.get('signal_type')
    price = signal_dict.get('price', 0)
    rsi = signal_dict.get('rsi', 50)
    ema_fast = signal_dict.get('ema_fast', 0)
    ema_slow = signal_dict.get('ema_slow', 0)
    market_strength_score = signal_dict.get('market_strength_score', 0)
    distance_to_buy = abs(float(signal_dict.get('distance_to_buy', 0)))
    distance_to_sell = abs(float(signal_dict.get('distance_to_sell', 0)))
    force_index = signal_dict.get('force_index', 0)
    trend = signal_dict.get('trend', 0)
    atr = signal_dict.get('atr', 0)
    value_up = signal_dict.get('value_up_channel', 0)
    value_down = signal_dict.get('value_down_channel', 0)
    value_size = signal_dict.get('value_size', 0)
    suggested_price = float(signal_dict.get('suggested_buy_long', 0)) if signal_type == 'LONG' else float(signal_dict.get('suggested_sell_short', 0))
    
    # === 趋势强度权重控制（核心修改）===
    trend_strength = signal_dict.get('trend_strength', 50)
    trend_is_stable = signal_dict.get('trend_is_stable', False)
    
    # 根据趋势强度设置不同的调整参数
    trend_strength_multiplier = 1.0  # 整体乘数
    trend_strength_bonus = 0.0       # 额外加减分
    max_score_cap = 10.0             # 最高分数上限
    
    if trend_strength >= 80:
        # 强趋势：大幅提高信号质量
        trend_strength_multiplier = 1.4  # 提高40%
        trend_strength_bonus = 2.0       # 额外+2分
        max_score_cap = 10.0             # 无上限
        details.append(f"🚀 强趋势状态(强度{trend_strength:.1f}分)：整体评分×1.4 + 额外+2.0分")
        
    elif trend_strength >= 60:
        # 中等趋势：适度提高信号质量
        trend_strength_multiplier = 1.2  # 提高20%
        trend_strength_bonus = 1.0       # 额外+1分
        max_score_cap = 9.0              # 最高9分
        details.append(f"📈 中等趋势(强度{trend_strength:.1f}分)：整体评分×1.2 + 额外+1.0分，最高9分")
        
    elif trend_strength >= 40:
        # 弱趋势或震荡：显著降低信号质量
        trend_strength_multiplier = 0.6  # 降低40%
        trend_strength_bonus = -1.0      # 额外-1分
        max_score_cap = 7.0              # 最高7分
        details.append(f"⚖️ 弱趋势/震荡(强度{trend_strength:.1f}分)：整体评分×0.6 - 1.0分，最高7分")
        
    else:
        # 无明显趋势：大幅降低信号质量
        trend_strength_multiplier = 0.4  # 降低60%
        trend_strength_bonus = -2.0      # 额外-2分
        max_score_cap = 5.0              # 最高5分
        details.append(f"🌫️ 无明显趋势(强度{trend_strength:.1f}分)：整体评分×0.4 - 2.0分，最高5分")
    
    # 趋势稳定性调整（仅在有趋势时考虑）
    if trend_strength >= 60:  # 中等以上趋势
        if trend_is_stable:
            trend_strength_bonus += 0.8
            details.append(f"🛡️ 趋势稳定：额外+0.8分")
        else:
            trend_strength_bonus -= 0.5
            details.append(f"⚠️ 趋势不稳定：额外-0.5分")
    
    # 1. 市场强度评分
    market_score = 0
    if market_strength_score == 1:
        market_score = 3.5
        details.append("✅ 市场强度坚挺")
        
        # 检查信号与市场强度的匹配
        if signal_type == 'SHORT':  # 做空信号与市场坚挺矛盾
            market_score -= 1.0
            details.append("⚠️ 做空信号与市场坚挺矛盾")
            
    elif market_strength_score == -1:
        market_score = -3.5
        details.append("❌ 市场强度疲软")
        
        if signal_type == 'LONG':  # 做多信号与市场疲软矛盾
            market_score -= 1.0
            details.append("⚠️ 做多信号与市场疲软矛盾")
    else:
        details.append("➖ 市场强度中性")
    
    # 应用趋势强度权重
    market_score_adjusted = market_score * trend_strength_multiplier
    score += market_score_adjusted
    
    # 2. RSI评估
    rsi_score = 0
    if signal_type == 'LONG':
        if rsi > 70:
            rsi_score = -2.0
            details.append("❌ RSI超买区")
        elif rsi > 65:
            rsi_score = -1.0
            details.append("⚠️ RSI接近超买")
        elif 40 < rsi < 65:
            rsi_score = 1.0
            details.append("✅ RSI多头健康区间")
        elif rsi < 40:
            rsi_score = 0.5
            details.append("⚠️ RSI偏弱但可能有反弹")
            
    elif signal_type == 'SHORT':
        if rsi < 30:
            rsi_score = -2.0
            details.append("❌ RSI超卖区")
        elif rsi < 35:
            rsi_score = -1.0
            details.append("⚠️ RSI接近超卖")
        elif 35 < rsi < 60:
            rsi_score = 1.0
            details.append("✅ RSI空头健康区间")
        elif rsi > 60:
            rsi_score = 0.5
            details.append("⚠️ RSI偏强但可能有回调")
    
    # 应用趋势强度权重（弱趋势时RSI权重降低）
    rsi_weight = trend_strength_multiplier
    if trend_strength < 60:  # 非强趋势时
        rsi_weight *= 0.8    # RSI重要性降低
    score += rsi_score * rsi_weight
    
    # 3. EMA排列评估
    ema_score = 0
    ema_details = ""
    
    if signal_type == 'LONG':
        if ema_fast > ema_slow:
            diff_percent = ((ema_fast - ema_slow) / ema_slow * 100) if ema_slow != 0 else 0
            if diff_percent > 1.0:
                ema_score = 2.5
                ema_details = f"✅ EMA强势多头排列(+{diff_percent:.2f}%)"
            elif diff_percent > 0.3:
                ema_score = 1.5
                ema_details = f"✅ EMA多头排列(+{diff_percent:.2f}%)"
            else:
                ema_score = 1.0
                ema_details = "✅ EMA轻微多头排列"
        else:
            ema_score = -2.0
            ema_details = "❌ EMA空头排列，与信号方向矛盾"
            
    elif signal_type == 'SHORT':
        if ema_fast < ema_slow:
            diff_percent = ((ema_slow - ema_fast) / ema_fast * 100) if ema_fast != 0 else 0
            if diff_percent > 1.0:
                ema_score = 2.5
                ema_details = f"✅ EMA强势空头排列(+{diff_percent:.2f}%)"
            elif diff_percent > 0.3:
                ema_score = 1.5
                ema_details = f"✅ EMA空头排列(+{diff_percent:.2f}%)"
            else:
                ema_score = 1.0
                ema_details = "✅ EMA轻微空头排列"
        else:
            ema_score = -2.0
            ema_details = "❌ EMA多头排列，与信号方向矛盾"
    
    details.append(ema_details)
    
    # 应用趋势强度权重（强趋势时EMA排列更重要）
    ema_weight = trend_strength_multiplier
    if trend_strength >= 70:  # 强趋势
        ema_weight *= 1.3
    elif trend_strength < 40:  # 无趋势
        ema_weight *= 0.7      # EMA重要性降低
    score += ema_score * ema_weight
    
    # 4. 价格位置评估（相对于买入/卖出触发点）
    distance_score = 0
    if signal_type == 'LONG':
        if distance_to_buy < 0.5 and distance_to_buy > 0:
            distance_score = 2.0
            details.append(f"✅ 做多点位极近({distance_to_buy:.2f})")
        elif distance_to_buy < 1.0:
            distance_score = 1.5
            details.append(f"✅ 做多点位接近({distance_to_buy:.2f})")
        elif distance_to_buy < 2.0:
            distance_score = 0.5
            details.append(f"⚠️ 做多点位中等距离({distance_to_buy:.2f})")
        else:
            distance_score = -1.0
            details.append(f"❌ 做多点位较远({distance_to_buy:.2f})")
        
        # 检查是否接近做空触发点（风险）
        if distance_to_sell < 0.5:
            distance_score -= 2.5
            details.append(f"❌ 极近做空触发点({distance_to_sell:.2f})，风险极高")
        elif distance_to_sell < 1.0:
            distance_score -= 2.0
            details.append(f"❌ 接近做空触发点({distance_to_sell:.2f})，风险高")
        elif distance_to_sell < 2.0:
            distance_score -= 1.0
            details.append(f"⚠️ 较近做空触发点({distance_to_sell:.2f})")
            
    elif signal_type == 'SHORT':
        if distance_to_sell < 0.5 and distance_to_sell > 0:
            distance_score = 2.0
            details.append(f"✅ 做空点位极近({distance_to_sell:.2f})")
        elif distance_to_sell < 1.0:
            distance_score = 1.5
            details.append(f"✅ 做空点位接近({distance_to_sell:.2f})")
        elif distance_to_sell < 2.0:
            distance_score = 0.5
            details.append(f"⚠️ 做空点位中等距离({distance_to_sell:.2f})")
        else:
            distance_score = -1.0
            details.append(f"❌ 做空点位较远({distance_to_sell:.2f})")
        
        # 检查是否接近做多触发点（风险）
        if distance_to_buy < 0.5:
            distance_score -= 2.5
            details.append(f"❌ 极近做多触发点({distance_to_buy:.2f})，风险极高")
        elif distance_to_buy < 1.0:
            distance_score -= 2.0
            details.append(f"❌ 接近做多触发点({distance_to_buy:.2f})，风险高")
        elif distance_to_buy < 2.0:
            distance_score -= 1.0
            details.append(f"⚠️ 较近做多触发点({distance_to_buy:.2f})")
    
    # 应用趋势强度权重
    score += distance_score * trend_strength_multiplier
    
    # 5. 力度指数评估
    if price > 0:
        force_score, force_desc = evaluate_force_index_general(force_index, price, signal_type)
        
        # 根据趋势强度调整力度权重
        force_weight = trend_strength_multiplier
        if trend_strength >= 70:  # 强趋势中力度更重要
            force_weight *= 1.2
        elif trend_strength < 40:  # 无趋势中力度重要性降低
            force_weight *= 0.8
        
        score += force_score * force_weight
        details.append(force_desc)
    else:
        details.append("⚠️ 价格无效，无法评估力度指数")
    
    # 6. 趋势一致性评估
    trend_score = 0
    if signal_type == 'LONG':
        if trend == 1:
            trend_score = 1.5
            details.append("✅ 趋势方向一致(上涨)")
        elif trend == -1:
            trend_score = -1.5
            details.append("❌ 趋势方向相反(下跌)")
        else:
            trend_score = 0
            details.append("➖ 趋势震荡中")
            
    elif signal_type == 'SHORT':
        if trend == -1:
            trend_score = 1.5
            details.append("✅ 趋势方向一致(下跌)")
        elif trend == 1:
            trend_score = -1.5
            details.append("❌ 趋势方向相反(上涨)")
        else:
            trend_score = 0
            details.append("➖ 趋势震荡中")
    
    # 趋势一致性在强趋势中加倍重要
    trend_consistency_weight = trend_strength_multiplier
    if trend_strength >= 70:
        trend_consistency_weight *= 1.5
    elif trend_strength < 40:
        trend_consistency_weight *= 0.7  # 无趋势时一致性不重要
    
    score += trend_score * trend_consistency_weight
    
    # 7. 波动性评估（ATR）
    if atr > 0 and price > 0:
        atr_percent = (atr / price * 100)
        atr_score = 0
        
        # 不同趋势环境下对波动性的要求不同
        if trend_strength >= 70:  # 强趋势
            if atr_percent > 0.4:
                atr_score = 0.8
                details.append(f"✅ 强趋势中波动性充足({atr_percent:.2f}%)")
            elif atr_percent > 0.2:
                atr_score = 0.3
                details.append(f"⚠️ 强趋势中波动性一般({atr_percent:.2f}%)")
            else:
                atr_score = -0.8
                details.append(f"❌ 强趋势中波动性不足({atr_percent:.2f}%)")
                
        elif trend_strength >= 40:  # 弱趋势
            if atr_percent > 0.6:
                atr_score = 0.5
                details.append(f"✅ 震荡中波动性较高({atr_percent:.2f}%)")
            elif atr_percent > 0.3:
                atr_score = 0
                details.append(f"➖ 震荡中波动性适中({atr_percent:.2f}%)")
            else:
                atr_score = -0.3
                details.append(f"⚠️ 震荡中波动性较低({atr_percent:.2f}%)")
                
        else:  # 无趋势
            if atr_percent > 0.8:
                atr_score = 0.3
                details.append(f"✅ 无趋势中波动性高({atr_percent:.2f}%)")
            else:
                atr_score = 0
                details.append(f"➖ 无趋势中波动性一般({atr_percent:.2f}%)")
        
        score += atr_score
    
    # 8. 通道位置评估
    if value_up > 0 and value_down > 0 and price > 0 and (value_up - value_down) > 0:
        position_in_channel = (price - value_down) / (value_up - value_down) * 100
        channel_score = 0
        
        if signal_type == 'LONG':
            if position_in_channel < 20:
                channel_score = 1.5
                details.append(f"✅ 通道底部位置({position_in_channel:.1f}%)")
            elif position_in_channel < 40:
                channel_score = 1.0
                details.append(f"✅ 通道中下部({position_in_channel:.1f}%)")
            elif position_in_channel < 60:
                channel_score = 0.5
                details.append(f"⚠️ 通道中部({position_in_channel:.1f}%)")
            elif position_in_channel < 80:
                channel_score = -0.5
                details.append(f"⚠️ 通道中上部({position_in_channel:.1f}%)")
            else:
                channel_score = -1.5
                details.append(f"❌ 通道顶部位置({position_in_channel:.1f}%)")
                
        elif signal_type == 'SHORT':
            if position_in_channel > 80:
                channel_score = 1.5
                details.append(f"✅ 通道顶部位置({position_in_channel:.1f}%)")
            elif position_in_channel > 60:
                channel_score = 1.0
                details.append(f"✅ 通道中上部({position_in_channel:.1f}%)")
            elif position_in_channel > 40:
                channel_score = 0.5
                details.append(f"⚠️ 通道中部({position_in_channel:.1f}%)")
            elif position_in_channel > 20:
                channel_score = -0.5
                details.append(f"⚠️ 通道中下部({position_in_channel:.1f}%)")
            else:
                channel_score = -1.5
                details.append(f"❌ 通道底部位置({position_in_channel:.1f}%)")
        
        # 通道位置权重根据趋势强度调整
        channel_weight = trend_strength_multiplier
        if trend_strength >= 70:
            channel_weight *= 1.2  # 强趋势中通道位置更重要
        elif trend_strength < 40:
            channel_weight *= 0.8  # 无趋势中通道位置重要性降低
        
        score += channel_score * channel_weight
    
    # ===== 新增：建议价格距离评估 =====
    print(f"==sug== {suggested_price} cur_price={price}")
    suggested_price_score = 0
    if suggested_price > 0 and price > 0:
        # 计算现价与建议价格的百分比距离
        price_distance_percent = abs((price - suggested_price) / suggested_price * 100)
        
        # 计算绝对距离（用于判断）
        price_distance = abs(price - suggested_price)
        
        # 根据ATR来标准化距离评估（相对于市场波动性）
        if atr > 0:
            atr_distance_ratio = price_distance / atr
        else:
            # 如果ATR无效，使用价格百分比
            atr_distance_ratio = price_distance_percent / 0.5  # 假设0.5%作为基准
        
        # 评估距离质量（越接近建议价格越好）
        if atr_distance_ratio < 0.2:  # 小于0.2个ATR
            suggested_price_score = 2.5
            details.append(f"🎯 极近建议价格(距离{price_distance:.2f}, {price_distance_percent:.2f}%, 约{atr_distance_ratio:.1f}ATR)")
        elif atr_distance_ratio < 0.5:  # 小于0.5个ATR
            suggested_price_score = 1.8
            details.append(f"✅ 接近建议价格(距离{price_distance:.2f}, {price_distance_percent:.2f}%, 约{atr_distance_ratio:.1f}ATR)")
        elif atr_distance_ratio < 1.0:  # 小于1个ATR
            suggested_price_score = 0.8
            details.append(f"⚠️ 中等距离建议价格(距离{price_distance:.2f}, {price_distance_percent:.2f}%, 约{atr_distance_ratio:.1f}ATR)")
        elif atr_distance_ratio < 1.5:  # 小于1.5个ATR
            suggested_price_score = -0.5
            details.append(f"⚠️ 较远建议价格(距离{price_distance:.2f}, {price_distance_percent:.2f}%, 约{atr_distance_ratio:.1f}ATR)")
        else:  # 大于1.5个ATR
            suggested_price_score = -1.5
            details.append(f"❌ 远离建议价格(距离{price_distance:.2f}, {price_distance_percent:.2f}%, 约{atr_distance_ratio:.1f}ATR)")
        
        # 额外检查：价格是否在建议价格的正确方向
        if signal_type == 'LONG':
            # 做多信号：当前价格应低于或接近建议价格
            if price < suggested_price:
                direction_bonus = 0.5
                suggested_price_score += direction_bonus
                details.append(f"📈 价格低于建议价，做多时机良好 +{direction_bonus:.1f}分")
            elif price > suggested_price:
                direction_penalty = -0.8
                suggested_price_score += direction_penalty
                details.append(f"⚠️ 价格高于建议价，做多需谨慎 {direction_penalty:.1f}分")
                
        elif signal_type == 'SHORT':
            # 做空信号：当前价格应高于或接近建议价格
            if price > suggested_price:
                direction_bonus = 0.5
                suggested_price_score += direction_bonus
                details.append(f"📉 价格高于建议价，做空时机良好 +{direction_bonus:.1f}分")
            elif price < suggested_price:
                direction_penalty = -0.8
                suggested_price_score += direction_penalty
                details.append(f"⚠️ 价格低于建议价，做空需谨慎 {direction_penalty:.1f}分")
        
        # 根据趋势强度调整建议价格距离的权重
        suggested_price_weight = trend_strength_multiplier
        if trend_strength >= 70:  # 强趋势中，接近建议价格更重要
            suggested_price_weight *= 1.3
            details.append("🚀 强趋势中，接近建议价格的重要性提高")
        elif trend_strength < 40:  # 无趋势中，位置重要性降低
            suggested_price_weight *= 0.7
            details.append("🌫️ 无趋势中，建议价格距离的重要性降低")
        
        score += suggested_price_score * suggested_price_weight
    else:
        details.append("⚠️ 缺少建议价格或现价数据，无法评估价格接近度")
    
    # 9. 添加趋势强度基础加分/减分
    score += trend_strength_bonus
    
    # 10. 趋势强度与信号类型的逻辑一致性检查
    if trend_strength >= 70:  # 强趋势环境
        if signal_type == 'LONG':
            # 强趋势中做多，逻辑一致
            consistency_bonus = 0.5
            score += consistency_bonus
            details.append(f"✨ 强趋势中做多，逻辑一致 +{consistency_bonus:.1f}分")
        elif signal_type == 'SHORT':
            # 强趋势中做空，需要特别谨慎
            details.append("⚠️ 强趋势中做空，需特别谨慎，确认下跌趋势")
    
    # === 应用趋势强度分数上限 ===
    score = min(score, max_score_cap)
    
    # 最终限制分数在0-10之间
    score = max(0, min(10, score))
    
    # 质量等级判断（根据最终分数）
    if score >= 8:
        quality_level = "🟢"
        quality_text = "优质信号"
    elif score >= 6:
        quality_level = "🟡"
        quality_text = "良好信号"
    elif score >= 4:
        quality_level = "🟠"
        quality_text = "一般信号"
    else:
        quality_level = "🔴"
        quality_text = "谨慎信号"
    
    # 添加趋势强度环境说明
    if trend_strength >= 80:
        trend_env = "强趋势"
    elif trend_strength >= 60:
        trend_env = "中等趋势"
    elif trend_strength >= 40:
        trend_env = "弱趋势"
    else:
        trend_env = "无趋势"
    
    quality_text += f" | {trend_env}环境"
    
    # 添加趋势稳定性的最终说明
    if trend_strength >= 60 and trend_is_stable:
        quality_text += " | 趋势稳定"
    elif trend_strength >= 60 and not trend_is_stable:
        quality_text += " | 趋势不稳定"
    
    # 添加建议价格信息（如果可用）
    if suggested_price > 0:
        distance_percent = abs((price - suggested_price) / suggested_price * 100)
        quality_text += f" | 距建议价:{distance_percent:.1f}%"
    
    return round(score, 1), details, quality_level, quality_text

def get_trading_recommendation(quality_score, signal_type):
    """根据质量评分获取交易建议
    
    参数：
        quality_score: 质量评分
        signal_type: 信号类型（LONG/SHORT）
        
    返回：
        dict: 包含操作建议的字典
    """
    if quality_score >= 8:
        return {
            "action": "强烈建议进场",
            "position_size": "标准仓位",
            "risk_level": "低风险",
            "suggestion": "信号质量优秀，可积极操作",
            "icon": "🟢"
        }
    elif quality_score >= 6:
        return {
            "action": "建议轻仓尝试",
            "position_size": "70%-80%仓位",
            "risk_level": "中低风险",
            "suggestion": "信号质量良好，可谨慎操作",
            "icon": "🟡"
        }
    elif quality_score >= 4:
        return {
            "action": "谨慎操作",
            "position_size": "50%以下仓位",
            "risk_level": "中高风险",
            "suggestion": "信号质量一般，需严格控制风险",
            "icon": "🟠"
        }
    else:
        return {
            "action": "建议观望",
            "position_size": "不建议持仓",
            "risk_level": "高风险",
            "suggestion": "信号质量较差，不建议进场",
            "icon": "🔴"
        }