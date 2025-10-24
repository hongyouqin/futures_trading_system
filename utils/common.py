import logging
import backtrader as bt


def classify_symbol(symbol: str) -> str:
    """自动分类期货品种到对应的参数组"""
    
    # 定义品种分类字典
    symbol_groups = {
        # 农产品组
        'agricultural': [
            'A0', 'B0', 'M0', 'Y0', 'P0', 'C0', 'CS0', 'JD0', 'RR0', 'RM0', 
            'OI0', 'RS0', 'WH0', 'RI0', 'JR0', 'LR0', 'PM0', 'CF0', 'CY0', 
            'SR0', 'AP0', 'CJ0', 'PK0'
        ],
        # 畜牧产品
        'livestock': [
            'LH0', 'LC0'
        ],
        # 黑色系
        'black_products': [
            'RB0', 'HC0', 'I0', 'J0', 'JM0', 'SF0', 'SM0', 'SS0'
        ],
        # 有色金属
        'nonferrous_metals': [
            'CU0', 'AL0', 'ZN0', 'PB0', 'NI0', 'SN0', 'BC0', 'SI0'
        ],
        # 贵金属
        'precious_metals': [
            'AU0', 'AG0'
        ],
        # 能源化工
        'energy_chemical': [
            'FU0', 'BU0', 'RU0', 'L0', 'V0', 'PP0', 'EG0', 'EB0', 'TA0', 
            'MA0', 'FG0', 'SA0', 'UR0', 'SP0', 'LU0', 'NR0', 'PG0', 'PF0',
            'PS0'
        ],
        # 股指期货
        'stock_index': [
            'IF0', 'IH0', 'IC0', 'IM0'
        ],
        # 国债期货
        'bond_futures': [
            'T0', 'TF0', 'TS0'
        ],
        # 其他品种
        'others': [
            'FB0', 'BB0', 'SH0', 'PX0', 'PR0', 'PL0', 'SC0', 'AO0', 'BR0', 
            'EC0', 'AD0', 'OP0', 'LG0'
        ]
    }
    
    # 查找品种所属分类
    for group, symbols in symbol_groups.items():
        if symbol in symbols:
            return group
    
    # 默认分类
    return 'agricultural'

def get_parameter_groups():
    """按品种特性分组，每组固定参数"""
    return {
        # 农产品组 - 中等偏长周期适应季节性
        'agricultural': {'short_ma': 21, 'long_ma': 34},
        # 畜牧产品 - 中等周期
        'livestock': {'short_ma': 13, 'long_ma': 34},
        # 黑色系 - 中等周期
        'black_products': {'short_ma': 13, 'long_ma': 34},
        # 有色金属 - 需要更敏感的参数
        'nonferrous_metals': {'short_ma': 13, 'long_ma': 21},
        # 贵金属 - 较长周期
        'precious_metals': {'short_ma': 21, 'long_ma': 34},
        # 能源化工 - 中等周期
        'energy_chemical': {'short_ma': 13, 'long_ma': 34},
        # 股指期货 - 较短周期
        'stock_index': {'short_ma': 8, 'long_ma': 21},
        # 国债期货 - 长周期低波动
        'bond_futures': {'short_ma': 21, 'long_ma': 55},
        # 其他品种 - 默认中等周期
        'others': {'short_ma': 13, 'long_ma': 34}
    }

# 测试分类函数
def test_symbol_classification():
    """测试品种分类"""
    test_symbols = ['RB0', 'CU0', 'IF0', 'A0', 'AU0', 'V0', 'LH0']
    
    print("品种分类测试:")
    print("=" * 50)
    for symbol in test_symbols:
        group = classify_symbol(symbol)
        params = get_parameter_groups().get(group)
        print(f"{symbol} -> {group}: 短期={params['short_ma']}, 长期={params['long_ma']}")

if __name__ == "__main__":
    test_symbol_classification()