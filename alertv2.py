import os
from dotenv import load_dotenv
from deso_sdk import DeSoDexClient, base58_check_encode
import schedule
import time
from datetime import datetime
import requests
from typing import Optional, Dict
# 加载环境变量
load_dotenv()

# 配置参数
IS_TESTNET = os.getenv('IS_TESTNET', 'false').lower() == 'true'
NODE_URL = "https://node.deso.org" if not IS_TESTNET else "https://test.deso.org"
SEED_PHRASE = os.getenv('DESO_SEED_PHRASE')
INDEX = int(os.getenv('INDEX', '0'))
BARK_KEY = os.getenv('BARK_KEY')

# 交易参数
TARGET_WALLET = os.getenv('TARGET_WALLET')
LARGE_ORDER_THRESHOLD = float(os.getenv('LARGE_ORDER_THRESHOLD', '100000'))  # 大额订单阈值
LARGE_ORDER_THRESHOLD_OPEN = float(os.getenv('LARGE_ORDER_THRESHOLD_OPEN', '100'))  # OPENFUND大额订单阈值
LARGE_ORDER_THRESHOLD_DESO = float(os.getenv('LARGE_ORDER_THRESHOLD_OPEN', '100'))  # DESO大额订单阈值,用来锚定USDC
MONITOR_INTERVAL = int(os.getenv('MONITOR_INTERVAL', '1'))  # 监控间隔（分钟）
SELL_DOSE = float(os.getenv('SELL_DOSE', '1'))  # 低价提示该搬砖了
SELL_DOSE_OPEN = float(os.getenv('SELL_DOSE_OPEN', '1'))  # OPENFUND低价提示该搬砖了

# 代币映射表（公钥 -> 代币名称）
TOKEN_MAPPING = {
    "FOCUS": "BC1YLjEayZDjAPitJJX4Boy7LsEfN3sWAkYb3hgE9kGBirztsc2re1N",
    "USDC": "BC1YLiwTN3DbkU8VmD7F7wXcRR1tFX6jDEkLyruHD2WsH3URomimxLX",
    "OPEN": "BC1YLj3zNA7hRAqBVkvsTeqw7oi4H6ogKiAFL1VXhZy6pYeZcZ6TDRY",
    "DESO": "BC1YLbnP7rndL92x7DbLp6bkUpCgKmgoHgz7xEbwhgHTps3ZrXA6LtQ"
}
# 反向映射表（公钥 -> 代币名称）用于快速查询
PUBKEY_TO_NAME = {v: k for k, v in TOKEN_MAPPING.items()}

# 修改原有常量定义
FOCUS_PUBKEY = TOKEN_MAPPING["FOCUS"]
USDC_PUBKEY = TOKEN_MAPPING["USDC"]
OPEN_PUBKEY = TOKEN_MAPPING["OPEN"]
DESO_PUBKEY = TOKEN_MAPPING["DESO"]


def send_notification(title: str, message: str) -> None:
    """发送通知（使用Bark）"""
    # Bark通知
    try:
        url = f"https://api.day.app/{BARK_KEY}/{title}/{message}"
        response = requests.get(url)
        if response.status_code != 200:
            print(f"Bark通知发送失败: {response.status_code}")
    except Exception as e:
        print(f"Bark通知发送失败: {e}")

def get_order_book(client: DeSoDexClient, coin1_pubkey: str, coin2_pubkey: str) -> Optional[Dict]:
    """获取订单簿数据"""
    try:
        order_book = client.get_limit_orders(
            coin1_creator_pubkey=coin1_pubkey,
            coin2_creator_pubkey=coin2_pubkey
        )

        if not order_book or 'Orders' not in order_book:
            print("获取订单簿失败: 返回数据格式错误")
            return None

        orders = order_book['Orders']
        buy_orders = [order for order in orders if order.get('OperationType') == 'BID']
        sell_orders = [order for order in orders if order.get('OperationType') == 'ASK']

        # 按价格排序
        buy_orders.sort(key=lambda x: float(x.get('Price')), reverse=True)
        sell_orders.sort(key=lambda x: float(x.get('Price')))

        # 转换公钥为代币名称
        coin1_name = PUBKEY_TO_NAME.get(coin1_pubkey, coin1_pubkey[:6])
        coin2_name = PUBKEY_TO_NAME.get(coin2_pubkey, coin2_pubkey[:6])
        print(f"币对: {coin1_name}/{coin2_name}")
        # 打印订单信息
        print(f"总订单数量: {len(orders)}")
        print(f"买单数量: {len(buy_orders)}")
        print(f"卖单数量: {len(sell_orders)}\n")

        return {
            'buy_orders': buy_orders,
            'sell_orders': sell_orders
        }

    except Exception as e:
        print(f"获取订单簿失败: {e}")
        return None

def check_price_alerts() -> None:
    """检查价格并发送提醒"""
    try:
        if not SEED_PHRASE:
            raise ValueError("请在.env文件中设置DESO_SEED_PHRASE环境变量")

        # 获取基准DESO价格
        deso_buy_price = get_deso_price()
        if deso_buy_price is None:
            print("未能获取有效的DESO价格")
            return

        # 定义监控配置
        token_configs = [
            {
                'coin_pubkey': FOCUS_PUBKEY,
                'threshold': LARGE_ORDER_THRESHOLD,
                'sell_dose': SELL_DOSE,
                'pair_name': 'FOCUS/USDC',
                'base_coin': USDC_PUBKEY
            },
            {
                'coin_pubkey': OPEN_PUBKEY,
                'threshold': LARGE_ORDER_THRESHOLD_OPEN,
                'sell_dose': SELL_DOSE_OPEN,
                'pair_name': 'OPEN/USDC',
                'base_coin': USDC_PUBKEY
            }
        ]

        # 创建共享客户端实例
        client = create_deso_client()
        
        for config in token_configs:
            # 搬砖检测（通过DESO中转）
            check_cross_pair_arbitrage(client, config, deso_buy_price)
            
            # 直接交易对检测
            check_direct_pair_orders(client, config)

    except Exception as e:
        error_msg = f"检查价格失败: {str(e)}"
        print(f"\n[{datetime.now()}] {error_msg}")
        send_notification("错误提醒", error_msg)

def get_deso_price() -> Optional[float]:
    """获取DESO基准买价"""
    client = create_deso_client()
    order_book = get_order_book(client, DESO_PUBKEY, USDC_PUBKEY)
    if not order_book or 'buy_orders' not in order_book:
        return None
    
    # 筛选符合阈值的大额买单
    large_buy_orders = [
        order for order in order_book['buy_orders']
        if float(order['Quantity']) >= LARGE_ORDER_THRESHOLD_DESO
    ]
    return max(float(order['Price']) for order in large_buy_orders) if large_buy_orders else None

def create_deso_client() -> DeSoDexClient:
    """创建并初始化DeSo客户端"""
    return DeSoDexClient(
        seed_phrase_or_hex=SEED_PHRASE,
        is_testnet=IS_TESTNET,
        index=INDEX,
        node_url=NODE_URL
    )

def check_cross_pair_arbitrage(client: DeSoDexClient, config: dict, deso_price: float) -> None:
    """检查跨交易对套利机会"""
    # 获取目标交易对订单簿
    order_book = get_order_book(client, config['coin_pubkey'], DESO_PUBKEY)
    if not order_book or 'sell_orders' not in order_book:
        return

    # 筛选大额卖单并转换计价
    large_sell_orders = [
        order for order in order_book['sell_orders']
        if float(order['Quantity']) >= config['threshold']
        and order['TransactorPublicKeyBase58Check'] != TARGET_WALLET
    ]
    
    # 转换价格为基准货币（USDC）
    arbitrage_opportunities = []
    for order in large_sell_orders:
        converted_price = float(order['Price']) * deso_price
        if converted_price < config['sell_dose']:
            arbitrage_opportunities.append({
                '原始价格': float(order['Price']),
                '转换价格': converted_price,
                '数量': float(order['Quantity']),
                '钱包': order['TransactorPublicKeyBase58Check']
            })

    # 发送通知
    if arbitrage_opportunities:
        message = f"{config['pair_name']}套利机会\n" + "\n".join(
            f"价格: {op['转换价格']:.4f} USDC\n数量: {op['数量']:.1f}\n钱包: {op['钱包'][:6]}..."
            for op in arbitrage_opportunities
        )
        send_notification("💰 套利提醒", message)

def check_direct_pair_orders(client: DeSoDexClient, config: dict) -> None:
    """检查直接交易对的大额订单"""
    order_book = get_order_book(client, config['coin_pubkey'], config['base_coin'])
    if not order_book or 'sell_orders' not in order_book:
        return

    # 找到目标钱包的最低报价
    target_orders = [
        order for order in order_book['sell_orders']
        if order['TransactorPublicKeyBase58Check'] == TARGET_WALLET
        and float(order['Quantity']) >= config['threshold']
    ]
    if not target_orders:
        return
    
    target_min_price = min(float(order['Price']) for order in target_orders)
    
    # 检测低价竞争订单
    competing_orders = [
        order for order in order_book['sell_orders']
        if order['TransactorPublicKeyBase58Check'] != TARGET_WALLET
        and float(order['Price']) < target_min_price
        and float(order['Quantity']) >= config['threshold']
    ]

    if competing_orders:
        message = f"{config['pair_name']}低价订单\n" + "\n".join(
            f"价格: {float(order['Price']):.6f}\n数量: {float(order['Quantity']):.1f}\n钱包: {order['TransactorPublicKeyBase58Check'][:6]}..."
            for order in competing_orders
        )
        send_notification("⚠️ 订单竞争", message)

def main() -> None:
    print(f"\n=== 订单簿监控启动 ===")
    print(f"目标钱包: {TARGET_WALLET}")
    print(f"大额阈值: {LARGE_ORDER_THRESHOLD}")
    print(f"监控间隔: {MONITOR_INTERVAL}分钟")
    print(f"运行环境: {'测试网' if IS_TESTNET else '主网'}")
    
    try:
        # 立即执行一次
        check_price_alerts()

        # 定时执行
        schedule.every(MONITOR_INTERVAL).minutes.do(check_price_alerts)

        print("\n监控已启动，按Ctrl+C停止...")
        while True:
            schedule.run_pending()
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n监控已停止")
    except Exception as e:
        error_msg = f"程序异常退出: {str(e)}"
        print(f"\n{error_msg}")
        send_notification("错误提醒", error_msg)

    #send_notification("订单簿提醒", "测试通知")

if __name__ == "__main__":
    main()


