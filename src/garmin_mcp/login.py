"""保存并验证个人 API 密钥，不支持账号密码登录。"""
import argparse
from getpass import getpass
from . import official,client

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--region',choices=client.REGIONS)
    args=p.parse_args()
    region=args.region or client.get_region()
    print('请在佳明设置中创建个人 API 密钥：'+official.key_page(region))
    print('密钥只显示一次，请安全保存；遗失后撤销旧密钥并创建新的。')
    key=getpass('输入个人 API 密钥（隐藏输入）：').strip()
    try:official.verify(key,region)
    except official.OfficialError as e:
        raise SystemExit(str(e))
    official.save_key(key)
    client.save_config(region=region)
    print('个人 API 验证成功。')

if __name__=='__main__':main()
