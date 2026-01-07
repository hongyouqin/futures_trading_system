

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

# 3. 改进你的 send_to_dingding 函数，使用更友好的格式
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
    trend = signal_dict.get('trend', 0)
    if trend == 1:
        trend_display = '📈 上涨'
    elif trend == -1:
        trend_display = '📉 下跌'
    else:
        trend_display = '➡️ 震荡'
    
    # ========== 新增：信号质量评估 ==========
    quality_score, quality_details, quality_level, quality_text = evaluate_signal_quality(signal_dict)
    recommendation = get_trading_recommendation(quality_score, signal_type)
    
    # ========== 计算止损点数 ==========
    atr = float(signal_dict.get('atr', 0))
    stop_loss_points = int(round(atr * 2))  # 2倍ATR，取整数
    trend_strong = float(signal_dict.get('trend_strong', 2))
    
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
- **趋势**：`{trend_display}`
- **趋势强度**：`{trend_strong:.2f}`

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
- **趋势**：`{trend_display}`
- **趋势强度**：`{trend_strong:.2f}`
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
- **趋势**：`{trend_display}`
- **趋势强度**：`{trend_strong:.2f}`
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
- **日趋势**：{main_contract_info}

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
    
    # 1. 市场强度评分（提高权重，最关键的因素）
    if market_strength_score == 1:
        score += 3.5  # 大幅提高权重（从2.0提高到3.5）
        details.append("✅ 市场强度坚挺（高权重+3.5）")
        
        # 当市场强度坚挺时，进一步检查信号与市场强度的一致性
        if signal_type == 'LONG':
            details.append("✅ 做多信号与市场强势一致")
        elif signal_type == 'SHORT':
            # 做空信号与市场强势矛盾，需要谨慎
            score -= 1.0  # 适当扣分
            details.append("⚠️ 做空信号与市场强势矛盾，需谨慎")
            
    elif market_strength_score == -1:
        score -= 3.5  # 同等权重降低（从-2.0到-3.5）
        details.append("❌ 市场强度疲软（高权重-3.5）")
        
        # 当市场疲软时，检查信号与市场状态的一致性
        if signal_type == 'SHORT':
            details.append("✅ 做空信号与市场疲软一致")
        elif signal_type == 'LONG':
            # 做多信号与市场疲软矛盾，风险更高
            score -= 1.5  # 额外扣分
            details.append("❌ 做多信号与市场疲软矛盾，风险高")
    else:
        details.append("➖ 市场强度中性（无加减分）")
    
    # 2. RSI评估（避免超买超卖区）
    # 增加与市场强度的联动评估
    rsi_weight = 1.0
    if market_strength_score == 1:
        # 市场强势时，RSI超买的容忍度提高
        rsi_weight = 0.8  # 降低RSI权重
    elif market_strength_score == -1:
        # 市场疲软时，RSI超卖的容忍度提高
        rsi_weight = 0.8  # 降低RSI权重
    
    if signal_type == 'LONG':
        if rsi > 70:
            score -= 2.0 * rsi_weight
            details.append(f"❌ RSI超买区{'（市场强势，风险略降）' if market_strength_score == 1 else ''}")
        elif rsi > 65:
            score -= 1.0 * rsi_weight
            details.append(f"⚠️ RSI接近超买{'（市场强势，影响较小）' if market_strength_score == 1 else ''}")
        elif 40 < rsi < 65:
            score += 1.0 * rsi_weight
            details.append(f"✅ RSI多头健康区间{'（市场强势，效果增强）' if market_strength_score == 1 else ''}")
        elif rsi < 40:
            score += 0.5 * rsi_weight
            details.append(f"⚠️ RSI偏弱但可能有反弹{'（市场强势，反弹概率增加）' if market_strength_score == 1 else ''}")
            
    elif signal_type == 'SHORT':
        if rsi < 30:
            score -= 2.0 * rsi_weight
            details.append(f"❌ RSI超卖区{'（市场疲软，风险略降）' if market_strength_score == -1 else ''}")
        elif rsi < 35:
            score -= 1.0 * rsi_weight
            details.append(f"⚠️ RSI接近超卖{'（市场疲软，影响较小）' if market_strength_score == -1 else ''}")
        elif 35 < rsi < 60:
            score += 1.0 * rsi_weight
            details.append(f"✅ RSI空头健康区间{'（市场疲软，效果增强）' if market_strength_score == -1 else ''}")
        elif rsi > 60:
            score += 0.5 * rsi_weight
            details.append(f"⚠️ RSI偏强但可能有回调{'（市场疲软，回调概率增加）' if market_strength_score == -1 else ''}")
    
    # 3. EMA排列评估
    # 增加市场强度对EMA排列的权重影响
    ema_weight = 1.0
    if abs(market_strength_score) == 1:
        ema_weight = 1.2  # 市场有明显趋势时，EMA排列更重要
    
    if signal_type == 'LONG':
        if ema_fast > ema_slow:
            diff_percent = ((ema_fast - ema_slow) / ema_slow * 100) if ema_slow != 0 else 0
            if diff_percent > 0.5:
                score += 2.0 * ema_weight
                details.append(f"✅ EMA强势多头排列(+{diff_percent:.2f}%){'（市场强势，加成更高）' if market_strength_score == 1 else ''}")
            else:
                score += 1.0 * ema_weight
                details.append(f"✅ EMA多头排列{'（市场强势，更加可靠）' if market_strength_score == 1 else ''}")
        else:
            penalty = -1.5
            if market_strength_score == 1:
                penalty = -2.0  # 市场强势时，EMA空头排列的矛盾更严重
            score += penalty * ema_weight
            details.append(f"❌ EMA空头排列，与信号方向矛盾{'（与市场强势严重矛盾）' if market_strength_score == 1 else ''}")
            
    elif signal_type == 'SHORT':
        if ema_fast < ema_slow:
            diff_percent = ((ema_slow - ema_fast) / ema_fast * 100) if ema_fast != 0 else 0
            if diff_percent > 0.5:
                score += 2.0 * ema_weight
                details.append(f"✅ EMA强势空头排列(+{diff_percent:.2f}%){'（市场疲软，加成更高）' if market_strength_score == -1 else ''}")
            else:
                score += 1.0 * ema_weight
                details.append(f"✅ EMA空头排列{'（市场疲软，更加可靠）' if market_strength_score == -1 else ''}")
        else:
            penalty = -1.5
            if market_strength_score == -1:
                penalty = -2.0  # 市场疲软时，EMA多头排列的矛盾更严重
            score += penalty * ema_weight
            details.append(f"❌ EMA多头排列，与信号方向矛盾{'（与市场疲软严重矛盾）' if market_strength_score == -1 else ''}")
    
    # 4. 价格位置评估（入场距离和触发风险）
    # 市场强度影响风险容忍度
    distance_weight = 1.0
    if abs(market_strength_score) == 1:
        distance_weight = 1.2  # 市场有趋势时，入场位置更重要
    
    if signal_type == 'LONG':
        # 检查做多入场距离
        if distance_to_buy < 1.0 and distance_to_buy > 0:
            bonus = 1.5
            if market_strength_score == 1:
                bonus = 1.8  # 市场强势时，接近入场点的优势更大
            score += bonus * distance_weight
            details.append(f"✅ 做多点位接近({distance_to_buy:.2f}){'（市场强势，优势放大）' if market_strength_score == 1 else ''}")
        elif distance_to_buy < 2.0:
            score += 0.5 * distance_weight
            details.append(f"⚠️ 做多点位中等距离({distance_to_buy:.2f})")
        else:
            score -= 0.5 * distance_weight
            details.append(f"❌ 做多点位较远({distance_to_buy:.2f}){'（市场强势仍有机会）' if market_strength_score == 1 else ''}")
        
        # 检查是否接近做空触发点（风险）
        if distance_to_sell < 1.0:
            penalty = -2.0
            if market_strength_score == -1:
                penalty = -2.5  # 市场疲软时，接近做空点的风险更大
            score += penalty * distance_weight
            details.append(f"❌ 接近做空触发点({distance_to_sell:.2f})，风险高{'（市场疲软，风险更高）' if market_strength_score == -1 else ''}")
        elif distance_to_sell < 2.0:
            score -= 1.0 * distance_weight
            details.append(f"⚠️ 较近做空触发点({distance_to_sell:.2f})")
            
    elif signal_type == 'SHORT':
        # 检查做空入场距离
        if distance_to_sell < 1.0 and distance_to_sell > 0:
            bonus = 1.5
            if market_strength_score == -1:
                bonus = 1.8  # 市场疲软时，接近入场点的优势更大
            score += bonus * distance_weight
            details.append(f"✅ 做空点位接近({distance_to_sell:.2f}){'（市场疲软，优势放大）' if market_strength_score == -1 else ''}")
        elif distance_to_sell < 2.0:
            score += 0.5 * distance_weight
            details.append(f"⚠️ 做空点位中等距离({distance_to_sell:.2f})")
        else:
            score -= 0.5 * distance_weight
            details.append(f"❌ 做空点位较远({distance_to_sell:.2f}){'（市场疲软仍有机会）' if market_strength_score == -1 else ''}")
        
        # 检查是否接近做多触发点（风险）
        if distance_to_buy < 1.0:
            penalty = -2.0
            if market_strength_score == 1:
                penalty = -2.5  # 市场强势时，接近做多点的风险更大
            score += penalty * distance_weight
            details.append(f"❌ 接近做多触发点({distance_to_buy:.2f})，风险高{'（市场强势，风险更高）' if market_strength_score == 1 else ''}")
        elif distance_to_buy < 2.0:
            score -= 1.0 * distance_weight
            details.append(f"⚠️ 较近做多触发点({distance_to_buy:.2f})")
    
    
    # 5. 力度指数评估（与市场强度联动）
    if price > 0:
        # 获取力度评估结果
        force_score, force_desc = evaluate_force_index_general(force_index, price, signal_type)
        
        # 根据市场强度调整力度权重
        force_weight = 0.8
        if abs(market_strength_score) == 1:
            force_weight = 1.0  # 市场有趋势时，力度指数更重要
        
        # 调整分数
        score += force_score * force_weight
        
        # 添加描述（包含市场强度信息）
        if market_strength_score == 1 and force_score > 0:
            force_desc += "（市场强势，力度更可靠）"
        elif market_strength_score == -1 and force_score > 0 and signal_type == 'SHORT':
            force_desc += "（市场疲软，下跌力度更可靠）"
        
        details.append(force_desc)
        
    else:
        details.append("⚠️ 价格无效，无法评估力度指数")

    # 6. 趋势一致性评估
    # 如果市场强度已经有明确指示，趋势评估的重要性相对降低
    trend_weight = 1.0
    if abs(market_strength_score) == 1:
        trend_weight = 0.7  # 市场强度已经提供了趋势信息

    if signal_type == 'LONG':
        if trend == 1:
            score += 1.0 * trend_weight
            details.append("✅ 趋势方向一致(上涨)" + f"{'（与市场强势叠加）' if market_strength_score == 1 else ''}")
        elif trend == -1:
            score -= 1.0 * trend_weight
            details.append("❌ 趋势方向相反(下跌)" + f"{'（与市场强势严重冲突）' if market_strength_score == 1 else ''}")
        else:
            details.append("➖ 趋势震荡中")
            
    elif signal_type == 'SHORT':
        if trend == -1:
            score += 1.0 * trend_weight
            details.append("✅ 趋势方向一致(下跌)" + f"{'（与市场疲软叠加）' if market_strength_score == -1 else ''}")
        elif trend == 1:
            score -= 1.0 * trend_weight
            details.append("❌ 趋势方向相反(上涨)" + f"{'（与市场疲软严重冲突）' if market_strength_score == -1 else ''}")
        else:
            details.append("➖ 趋势震荡中")
    
    # 7. 波动性评估（ATR）
    if atr > 0:
        atr_percent = (atr / price * 100) if price != 0 else 0
        
        # 市场强度影响对波动性的要求
        if abs(market_strength_score) == 1:
            # 有趋势时，需要足够的波动性
            if atr_percent > 0.3:
                score += 0.5
                details.append(f"✅ 趋势中波动性充足({atr_percent:.2f}%)")
            else:
                score -= 0.8
                details.append(f"❌ 趋势中波动性不足({atr_percent:.2f}%)")
        else:
            # 无趋势时，波动性要求可适当降低
            if atr_percent > 0.5:
                score += 0.5
                details.append(f"✅ 波动性充足({atr_percent:.2f}%)")
            elif atr_percent > 0.2:
                details.append(f"➖ 波动性适中({atr_percent:.2f}%)")
            else:
                score -= 0.5
                details.append(f"⚠️ 波动性较低({atr_percent:.2f}%)")
    
    # 8. 通道位置评估
    if value_up > 0 and value_down > 0 and price > 0:
        channel_middle = (value_up + value_down) / 2
        position_in_channel = (price - value_down) / (value_up - value_down) * 100 if (value_up - value_down) != 0 else 50
        
        # 市场强度影响通道位置的重要性
        channel_weight = 1.0
        if abs(market_strength_score) == 1:
            channel_weight = 1.3  # 有趋势时，通道位置更重要

        if signal_type == 'LONG':
            if position_in_channel < 30:
                score += 1.0 * channel_weight
                details.append(f"✅ 通道底部位置({position_in_channel:.1f}%){'（市场强势，反弹动力强）' if market_strength_score == 1 else ''}")
            elif position_in_channel < 50:
                score += 0.5 * channel_weight
                details.append(f"⚠️ 通道中下部({position_in_channel:.1f}%)")
            elif position_in_channel > 70:
                score -= 1.5 * channel_weight
                details.append(f"❌ 通道顶部位置({position_in_channel:.1f}%){'（市场强势，但位置不佳）' if market_strength_score == 1 else ''}")
            else:
                details.append(f"➖ 通道中部({position_in_channel:.1f}%)")
                
        elif signal_type == 'SHORT':
            if position_in_channel > 70:
                score += 1.0 * channel_weight
                details.append(f"✅ 通道顶部位置({position_in_channel:.1f}%){'（市场疲软，下跌动力强）' if market_strength_score == -1 else ''}")
            elif position_in_channel > 50:
                score += 0.5 * channel_weight
                details.append(f"⚠️ 通道中上部({position_in_channel:.1f}%)")
            elif position_in_channel < 30:
                score -= 1.5 * channel_weight
                details.append(f"❌ 通道底部位置({position_in_channel:.1f}%){'（市场疲软，但位置不佳）' if market_strength_score == -1 else ''}")
            else:
                details.append(f"➖ 通道中部({position_in_channel:.1f}%)")
    
    # 9. 新增：市场强度综合评估（信号与市场强度的匹配度）
    if abs(market_strength_score) == 1:
        # 检查信号类型与市场强度的匹配度
        if (market_strength_score == 1 and signal_type == 'LONG') or \
           (market_strength_score == -1 and signal_type == 'SHORT'):
            score += 0.5  # 额外加分
            details.append(f"✨ 信号与市场强度完美匹配")
        else:
            details.append("⚠️ 信号方向与市场强度不匹配，需谨慎")
    
    # 限制分数在0-10之间
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