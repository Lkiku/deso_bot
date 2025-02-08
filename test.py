import os
from dotenv import load_dotenv
from deso_sdk import DeSoDexClient, base58_check_encode
from pprint import pprint

# 加载环境变量
load_dotenv()

def get_order_book(client, coin1_pubkey: str, coin2_pubkey: str):
    """
    获取两个代币之间的订单簿数据
    
    Args:
        coin1_pubkey: 第一个代币创建者的公钥
        coin2_pubkey: 第二个代币创建者的公钥
    """
    
    try:
        # 获取订单簿数据
        order_book = client.get_limit_orders(
            coin1_creator_pubkey=coin1_pubkey,
            coin2_creator_pubkey=coin2_pubkey
        )

        # 解析订单数据
        if 'Orders' in order_book:
            orders = order_book['Orders']
            buy_orders = [order for order in orders if order.get('OperationType') == 'BID']
            sell_orders = [order for order in orders if order.get('OperationType') == 'ASK']

            # 买单按照价格由大到小排序
            buy_orders.sort(key=lambda x: float(x.get('Price')), reverse=True)
            # 卖单按照价格由大到小排序
            sell_orders.sort(key=lambda x: float(x.get('Price')), reverse=True)

            print(f"\n总订单数量: {len(orders)}")
            print(f"买单数量: {len(buy_orders)}")
            print(f"卖单数量: {len(sell_orders)}")

            print("\n=== 卖单列表 ===")
            for order in sell_orders[-20:]:  # 只显示最后10个卖单
                price = round(float(order.get('Price')), 12)
                print(f"价格: {price}, "
                      f"数量: {round(float(order.get('Quantity')), 1):.1f}, "
                    #   f"订单ID: {order.get('OrderID')},"
                      f"钱包公钥: {order.get('TransactorPublicKeyBase58Check')}")
            
            print("\n=== 买单列表 ===")
            for order in buy_orders[:20]:  # 只显示前5个买单
                price = round(float(order.get('Price')), 12)
                print(f"价格: {price}, "
                      f"数量: {round(float(order.get('Quantity')), 1):.1f}, "
                    #   f"订单ID: {order.get('OrderID')}")
                      f"钱包公钥: {order.get('TransactorPublicKeyBase58Check')}")

        return order_book

    except Exception as e:
        print(f"获取订单簿失败: {e}")
        return None

def main():
    # This is very important: If you want to run on mainnet, you must switch this to false.
    # This will switch several other params to the right values.
    IS_TESTNET = False
    # You can set any DeSo node you want. The nodes here are the canonical testnet and mainnet
    # ones that a lot of people use for testing. If you don't pass a node_url to the DesoDexClient
    # it will default to one of these depending on the value of is_testnet. We specify them here
    # explicitly just to make you aware that you can set it manually if you want.
    NODE_URL = "https://test.deso.org"
    if not IS_TESTNET:
       NODE_URL = "https://node.deso.org"

    # Print the params
    print(f"IS_TESTNET={IS_TESTNET}, NODE_URL={NODE_URL}")

    # 从环境变量获取种子短语
    SEED_PHRASE_OR_HEX = os.getenv('DESO_SEED_PHRASE')
    INDEX = 0
    if not SEED_PHRASE_OR_HEX:
        raise ValueError("请在.env文件中设置DESO_SEED_PHRASE环境变量")

    client = DeSoDexClient(
        is_testnet=IS_TESTNET,
        seed_phrase_or_hex=SEED_PHRASE_OR_HEX,
        index=INDEX,
        node_url=NODE_URL)
    
    string_pubkey = base58_check_encode(client.deso_keypair.public_key, IS_TESTNET)
    print(f'Public key for seed: {string_pubkey}')

    focus_pubkey = "BC1YLjEayZDjAPitJJX4Boy7LsEfN3sWAkYb3hgE9kGBirztsc2re1N"
    usdc_pubkey = "BC1YLiwTN3DbkU8VmD7F7wXcRR1tFX6jDEkLyruHD2WsH3URomimxLX"

    # try:
    #     print(f"\n---- Get balances ----")
    #     print(f'Getting $openfund and $FOCUS balances for pubkey: {string_pubkey}')
    #     balances = client.get_token_balances(
    #         user_public_key=string_pubkey,
    #         creator_public_keys=[focus_pubkey, "FOCUS", string_pubkey],
    #     )
    #     pprint(balances)
    # except Exception as e:
    #     print(f"ERROR: Get token balances call failed: {e}")

    order_book_1 = get_order_book(client, focus_pubkey, usdc_pubkey)
    # order_book_2 = get_order_book(client, usdc_pubkey, focus_pubkey)

    # print("\n=== 订单簿 ===")
    # print(order_book)

    # import json
    # with open('order_book.json', 'w') as f:
    #     json.dump(order_book, f, indent=4, ensure_ascii=False)


if __name__ == "__main__":
    main()