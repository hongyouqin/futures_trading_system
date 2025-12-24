

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

def format_signal_as_markdown(signal_dict, symbol=None, symbol_to_name_dict=None):
    """将交易信号格式化为钉钉Markdown消息（增强版）"""
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
    
    # 构建完整的Markdown消息
    markdown_text = f"""### 🚀 期货交易信号通知

**{signal_display}** | **{action_text}**

---

#### 📋 合约信息
- **合约名称**：{symbol_name if symbol_name else '未知'}
- **合约代码**：`{symbol if symbol else 'N/A'}`
- **信号时间**：{time_str}

#### 📊 价格与趋势
- **当前价格**：`{signal_dict.get('price', 0):.2f}`
- **趋势方向**：{trend_display}
- **力度指数**：`{signal_dict.get('force_index', 0):.2f}`

#### 🎯 技术指标
- **EMA快线**：`{signal_dict.get('ema_fast', 0):.2f}`
- **EMA慢线**：`{signal_dict.get('ema_slow', 0):.2f}`
- **RSI指标**：`{signal_dict.get('rsi', 0):.2f}`
- **ATR波动**：`{signal_dict.get('atr', 0):.2f}`

#### 📈 价值通道
- **上通道**：`{signal_dict.get('value_up_channel', 0):.2f}`
- **下通道**：`{signal_dict.get('value_down_channel', 0):.2f}`
- **通道大小**：`{signal_dict.get('value_size', 0)}`

#### 🎮 交易建议
- **做多入场**：`{float(signal_dict.get('suggested_buy_long', 0)):.2f}`
- **距做多点**：`{float(signal_dict.get('distance_to_buy', 0)):.2f}`
- **做空入场**：`{float(signal_dict.get('suggested_sell_short', 0)):.2f}`
- **距做空点**：`{float(signal_dict.get('distance_to_sell', 0)):.2f}`

#### ⚡ 市场强度
- **强度描述**：{signal_dict.get('market_strength', 'N/A')}
- **强度评分**：{signal_dict.get('market_strength_score', 0)}

---

> ⚠️ **风险提示**：投资有风险，入市需谨慎  
"""
    return markdown_text

# def send_custom_robot_group_message(access_token, secret, msg, at_user_ids=None, at_mobiles=None, is_at_all=False):
#     """
#     发送钉钉自定义机器人群消息
#     :param access_token: 机器人webhook的access_token
#     :param secret: 机器人安全设置的加签secret
#     :param msg: 消息内容
#     :param at_user_ids: @的用户ID列表
#     :param at_mobiles: @的手机号列表
#     :param is_at_all: 是否@所有人
#     :return: 钉钉API响应
#     """
#     timestamp = str(round(time.time() * 1000))
#     string_to_sign = f'{timestamp}\n{secret}'
#     hmac_code = hmac.new(secret.encode('utf-8'), string_to_sign.encode('utf-8'), digestmod=hashlib.sha256).digest()
#     sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))

#     url = f'https://oapi.dingtalk.com/robot/send?access_token={access_token}&timestamp={timestamp}&sign={sign}'

#     body = {
#         "at": {
#             "isAtAll": str(is_at_all).lower(),
#             "atUserIds": at_user_ids or [],
#             "atMobiles": at_mobiles or []
#         },
#         "text": {
#             "content": msg
#         },
#         "msgtype": "text"
#     }
#     headers = {'Content-Type': 'application/json'}
#     resp = requests.post(url, json=body, headers=headers)
#     print("钉钉自定义机器人群消息响应：%s", resp.text)
#     # logging.info("钉钉自定义机器人群消息响应：%s", resp.text)
#     return resp.json()

