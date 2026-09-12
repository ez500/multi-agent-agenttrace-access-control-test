import os
import msal
import requests
from typing import Optional
from dotenv import load_dotenv
from flask import Flask, request, jsonify

load_dotenv()

app = Flask(__name__)

def get_access_token(tenant_id: str, client_id: str, client_secret: str, scope: str) -> Optional[str]:
    """使用 MSAL 取得 Access Token"""
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    msal_app = msal.ConfidentialClientApplication(
        client_id,
        authority=authority,
        client_credential=client_secret
    )
    result = msal_app.acquire_token_for_client(scopes=[scope])

    if "access_token" in result:
        return result["access_token"]

    print("\n❌ 取得 Token 失敗！詳細錯誤訊息：")
    print(f"Error: {result.get('error')}")
    print(f"Description: {result.get('error_description')}\n")

    return None

def call_llm_api(endpoint: str, access_token: str, subscription_key: str, prompt: str) -> dict:
    """呼叫 LLM API 並回傳結果字典"""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Ocp-Apim-Subscription-Key": subscription_key,
        "Content-Type": "application/json"
    }

    payload = {
        "model": "global.anthropic.claude-sonnet-4-6",
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "stream": False
    }

    try:
        response = requests.post(endpoint, headers=headers, json=payload)

        # 如果發生 400 錯誤
        if not response.ok:
            print(f"❌ API 拒絕請求，詳細原因: {response.text}")

        response.raise_for_status()
        return response.json()

    except requests.exceptions.RequestException as e:
        return {"error": str(e), "details": response.text if response else "No response"}


@app.route('/api/chat', methods=['POST'])
def chat():
    """處理前端或外部傳來的 POST 請求"""
    # 取得前端傳來的 JSON 資料 (例如: {"prompt": "你好！"})
    data = request.get_json()
    prompt = data.get("prompt", "Hello, LLM!") if data else "Hello, LLM!"

    # 讀取環境變數
    tenant_id = os.getenv("TENANT_ID")
    client_id = os.getenv("CLIENT_ID")
    client_secret = os.getenv("CLIENT_SECRET")
    scope = os.getenv("SCOPE", "https://cognitiveservices.azure.com/.default")
    subscription_key = os.getenv("SUBSCRIPTION_KEY")
    llm_endpoint = os.getenv("LLM_ENDPOINT")

    if not all([tenant_id, client_id, client_secret, subscription_key, llm_endpoint]):
        return jsonify({"error": "伺服器環境變數設定不完整"}), 500

    # 1. 取得 Token
    token = get_access_token(tenant_id, client_id, client_secret, scope)
    if not token:
        return jsonify({"error": "無法取得授權 Token"}), 401

    # 2. 呼叫 LLM API
    result = call_llm_api(llm_endpoint, token, subscription_key, prompt)

    if "error" in result:
        return jsonify(result), 500

    # 3. 回傳 LLM 的回應給客戶端
    return jsonify({
        "status": "success",
        "prompt": prompt,
        "response": result
    })

if __name__ == '__main__':
    # 啟動 Flask 伺服器
    app.run(host='0.0.0.0', port=5001, debug=True)
