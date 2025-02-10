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
LARGE_ORDER_THRESHOLD_OPEN = float(os.getenv('LARGE_ORDER_THRESHOLD_OPEN', '100'))  # 大额订单阈值
MONITOR_INTERVAL = int(os.getenv('MONITOR_INTERVAL', '1'))  # 监控间隔（分钟）

# 代币地址
FOCUS_PUBKEY = "BC1YLjEayZDjAPitJJX4Boy7LsEfN3sWAkYb3hgE9kGBirztsc2re1N"
USDC_PUBKEY = "BC1YLiwTN3DbkU8VmD7F7wXcRR1tFX6jDEkLyruHD2WsH3URomimxLX"
OPEN_PUBKEY = "BC1YLj3zNA7hRAqBVkvsTeqw7oi4H6ogKiAFL1VXhZy6pYeZcZ6TDRY"
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

        # 打印订单信息
        print(f"\n总订单数量: {len(orders)}")
        print(f"买单数量: {len(buy_orders)}")
        print(f"卖单数量: {len(sell_orders)}")

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
        for ii in range(2):
            client = DeSoDexClient(
                seed_phrase_or_hex=SEED_PHRASE,
                is_testnet=IS_TESTNET,
                index=INDEX,
                node_url=NODE_URL
            )

            # 打印当前账号信息
            current_pubkey = base58_check_encode(client.deso_keypair.public_key, IS_TESTNET)
            print(f'\n当前账号公钥: {current_pubkey}')

            # 获取订单簿
            if ii == 0:
                order_book = get_order_book(client, FOCUS_PUBKEY, USDC_PUBKEY)
            else:
                order_book = get_order_book(client, OPEN_PUBKEY, USDC_PUBKEY)
            if not order_book or 'sell_orders' not in order_book:
                return

            sell_orders = order_book['sell_orders']

            # 找到目标钱包的最低价格
            target_orders = [order for order in sell_orders if order['TransactorPublicKeyBase58Check'] == TARGET_WALLET]
            if not target_orders:
                print(f"未找到目标钱包 {TARGET_WALLET} 的订单")
                return

            # 先筛选出所有的大额订单

            if ii == 0:
                large_orders = [order for order in sell_orders if float(order['Quantity']) >= LARGE_ORDER_THRESHOLD]
            else:
                large_orders = [order for order in sell_orders if float(order['Quantity']) >= LARGE_ORDER_THRESHOLD_OPEN]
                # for order in sell_orders:
                #     print(order['TransactorPublicKeyBase58Check'],float(order['Price']),float(order['Quantity']))
            print(f"大额订单数量: {len(large_orders)}")

            # 找出target_min_price
            target_min_price = min(float(order['Price']) for order in large_orders if order['TransactorPublicKeyBase58Check'] == TARGET_WALLET)
            print(f"目标钱包最低价格: {target_min_price:.6f}")

            # 检查其他钱包的大额订单
            found_orders = []
            for order in large_orders:
                if order['TransactorPublicKeyBase58Check'] != TARGET_WALLET:
                    price = float(order['Price'])
                    quantity = float(order['Quantity'])

                    if price < target_min_price:
                        found_orders.append({
                            'price': price,
                            'quantity': quantity,
                            'wallet': order['TransactorPublicKeyBase58Check']
                        })

            if found_orders:
                message = "发现低价大额订单！\n" + "\n".join(
                    f"价格: {order['price']:.6f}\n数量: {order['quantity']:.1f}\n钱包: {order['wallet'][:8]}..."
                    for order in found_orders
                )
                send_notification("订单簿提醒", message)
                print(f"\n[{datetime.now()}] {message}")

    except Exception as e:
        error_msg = f"检查价格失败: {str(e)}"
        print(f"\n[{datetime.now()}] {error_msg}")
        send_notification("错误提醒", error_msg)

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


