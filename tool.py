

import base64
import hashlib
import hmac
import time
import urllib
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
    
    # ========== 根据信号类型显示交易建议 ==========
    trading_suggestion_text = ""
    if signal_type == 'LONG':
        suggested_price = float(signal_dict.get('suggested_buy_long', 0))
        distance = float(signal_dict.get('distance_to_buy', 0))
        trading_suggestion_text = f"""#### 🎮 交易建议
- **当前价格**：`{signal_dict.get('price', 0):.2f}`
- **做多入场**：`{suggested_price:.2f}`
- **距做多点**：`{distance:.2f}`
- **止损点数**：`{stop_loss_points}`
- **力度指数**：`{signal_dict.get('force_index', 0):.2f}`
- **趋势**：`{trend_display}`
"""
    elif signal_type == 'SHORT':
        suggested_price = float(signal_dict.get('suggested_sell_short', 0))
        distance = float(signal_dict.get('distance_to_sell', 0))
        trading_suggestion_text = f"""#### 🎮 交易建议
- **当前价格**：`{signal_dict.get('price', 0):.2f}`
- **做空入场**：`{suggested_price:.2f}`
- **距做空点**：`{distance:.2f}`
- **止损点数**：`{stop_loss_points}`
- **力度指数**：`{signal_dict.get('force_index', 0):.2f}`
- **趋势**：`{trend_display}`
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
"""
    
    # ========== 构建Markdown消息 ==========
    markdown_text = f"""### 🚀 期货交易信号通知

**{signal_display}** | **{action_text}**

---

#### 📋 合约信息
- **合约名称**：{symbol_name if symbol_name else '未知'}
- **合约代码**：`{symbol if symbol else 'N/A'}`
- **信号时间**：{time_str}
- **信号质量**：{quality_level} **{quality_score}/10** ({quality_text})

{trading_suggestion_text}

### 💡 操作建议
- {recommendation['icon']} **{recommendation['action']}**
- 📊 **建议仓位**：{recommendation['position_size']}
- ⚠️ **风险等级**：{recommendation['risk_level']}
- 💡 **策略建议**：{recommendation['suggestion']}

#### 🎯 技术指标
- **EMA快线**：`{signal_dict.get('ema_fast', 0):.2f}`
- **EMA慢线**：`{signal_dict.get('ema_slow', 0):.2f}`
- **RSI指标**：`{signal_dict.get('rsi', 0):.2f}`
- **ATR波动**：`{signal_dict.get('atr', 0):.2f}`

#### 📈 价值通道
- **上通道**：`{signal_dict.get('value_up_channel', 0):.2f}`
- **下通道**：`{signal_dict.get('value_down_channel', 0):.2f}`
- **通道大小**：`{signal_dict.get('value_size', 0)}`

#### 🏆 信号质量评估
**评估详情：**
"""
    
    # 添加评估详情
    for detail in quality_details:
        markdown_text += f"- {detail}\n"
    
    # 添加风险提示
    markdown_text += f"""
---

> ⚠️ **风险提示**：投资有风险，入市需谨慎  
> 📊 **信号质量**仅供参考，请结合实盘情况决策
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
    
    # 1. 市场强度评分（最重要的因素之一）
    if market_strength_score == 1:
        score += 2.0
        details.append("✅ 市场强度坚挺")
    elif market_strength_score == -1:
        score -= 2.0
        details.append("❌ 市场强度疲软")
    else:
        details.append("➖ 市场强度中性")
    
    # 2. RSI评估（避免超买超卖区）
    if signal_type == 'LONG':
        if rsi > 70:
            score -= 2.0
            details.append("❌ RSI超买区，回调风险高")
        elif rsi > 65:
            score -= 1.0
            details.append("⚠️ RSI接近超买")
        elif 40 < rsi < 65:
            score += 1.0
            details.append("✅ RSI多头健康区间")
        elif rsi < 40:
            score += 0.5
            details.append("⚠️ RSI偏弱但可能有反弹")
            
    elif signal_type == 'SHORT':
        if rsi < 30:
            score -= 2.0
            details.append("❌ RSI超卖区，反弹风险高")
        elif rsi < 35:
            score -= 1.0
            details.append("⚠️ RSI接近超卖")
        elif 35 < rsi < 60:
            score += 1.0
            details.append("✅ RSI空头健康区间")
        elif rsi > 60:
            score += 0.5
            details.append("⚠️ RSI偏强但可能有回调")
    
    # 3. EMA排列评估
    if signal_type == 'LONG':
        if ema_fast > ema_slow:
            diff_percent = ((ema_fast - ema_slow) / ema_slow * 100) if ema_slow != 0 else 0
            if diff_percent > 0.5:
                score += 2.0
                details.append(f"✅ EMA强势多头排列(+{diff_percent:.2f}%)")
            else:
                score += 1.0
                details.append("✅ EMA多头排列")
        else:
            score -= 1.5
            details.append("❌ EMA空头排列，与信号方向矛盾")
            
    elif signal_type == 'SHORT':
        if ema_fast < ema_slow:
            diff_percent = ((ema_slow - ema_fast) / ema_fast * 100) if ema_fast != 0 else 0
            if diff_percent > 0.5:
                score += 2.0
                details.append(f"✅ EMA强势空头排列(+{diff_percent:.2f}%)")
            else:
                score += 1.0
                details.append("✅ EMA空头排列")
        else:
            score -= 1.5
            details.append("❌ EMA多头排列，与信号方向矛盾")
    
    # 4. 价格位置评估（入场距离和触发风险）
    if signal_type == 'LONG':
        # 检查做多入场距离
        if distance_to_buy < 1.0 and distance_to_buy > 0:
            score += 1.5
            details.append(f"✅ 做多点位接近({distance_to_buy:.2f})")
        elif distance_to_buy < 2.0:
            score += 0.5
            details.append(f"⚠️ 做多点位中等距离({distance_to_buy:.2f})")
        else:
            score -= 0.5
            details.append(f"❌ 做多点位较远({distance_to_buy:.2f})")
        
        # 检查是否接近做空触发点（风险）
        if distance_to_sell < 1.0:
            score -= 2.0
            details.append(f"❌ 接近做空触发点({distance_to_sell:.2f})，风险高")
        elif distance_to_sell < 2.0:
            score -= 1.0
            details.append(f"⚠️ 较近做空触发点({distance_to_sell:.2f})")
            
    elif signal_type == 'SHORT':
        # 检查做空入场距离
        if distance_to_sell < 1.0 and distance_to_sell > 0:
            score += 1.5
            details.append(f"✅ 做空点位接近({distance_to_sell:.2f})")
        elif distance_to_sell < 2.0:
            score += 0.5
            details.append(f"⚠️ 做空点位中等距离({distance_to_sell:.2f})")
        else:
            score -= 0.5
            details.append(f"❌ 做空点位较远({distance_to_sell:.2f})")
        
        # 检查是否接近做多触发点（风险）
        if distance_to_buy < 1.0:
            score -= 2.0
            details.append(f"❌ 接近做多触发点({distance_to_buy:.2f})，风险高")
        elif distance_to_buy < 2.0:
            score -= 1.0
            details.append(f"⚠️ 较近做多触发点({distance_to_buy:.2f})")
    
    
    # 5. 力度指数评估
    if price > 0:
        # 获取力度评估结果
        force_score, force_desc = evaluate_force_index_general(force_index, price, signal_type)
        
        # 调整分数（力度评估占较大权重）
        score += force_score * 0.8  # 力度评估对总分的权重
        
        # 添加描述
        details.append(force_desc)
        
    else:
        details.append("⚠️ 价格无效，无法评估力度指数")

    # 6. 趋势一致性评估
    if signal_type == 'LONG':
        if trend == 1:
            score += 1.0
            details.append("✅ 趋势方向一致(上涨)")
        elif trend == -1:
            score -= 1.0
            details.append("❌ 趋势方向相反(下跌)")
        else:
            details.append("➖ 趋势震荡中")
            
    elif signal_type == 'SHORT':
        if trend == -1:
            score += 1.0
            details.append("✅ 趋势方向一致(下跌)")
        elif trend == 1:
            score -= 1.0
            details.append("❌ 趋势方向相反(上涨)")
        else:
            details.append("➖ 趋势震荡中")
    
    # 7. 波动性评估（ATR）
    if atr > 0:
        atr_percent = (atr / price * 100) if price != 0 else 0
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
        
        if signal_type == 'LONG':
            if position_in_channel < 30:
                score += 1.0
                details.append(f"✅ 通道底部位置({position_in_channel:.1f}%)")
            elif position_in_channel < 50:
                score += 0.5
                details.append(f"⚠️ 通道中下部({position_in_channel:.1f}%)")
            elif position_in_channel > 70:
                score -= 1.5
                details.append(f"❌ 通道顶部位置({position_in_channel:.1f}%)")
            else:
                details.append(f"➖ 通道中部({position_in_channel:.1f}%)")
                
        elif signal_type == 'SHORT':
            if position_in_channel > 70:
                score += 1.0
                details.append(f"✅ 通道顶部位置({position_in_channel:.1f}%)")
            elif position_in_channel > 50:
                score += 0.5
                details.append(f"⚠️ 通道中上部({position_in_channel:.1f}%)")
            elif position_in_channel < 30:
                score -= 1.5
                details.append(f"❌ 通道底部位置({position_in_channel:.1f}%)")
            else:
                details.append(f"➖ 通道中部({position_in_channel:.1f}%)")
    
    # 限制分数在0-10之间
    score = max(0, min(10, score))
    
    # 质量等级判断
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