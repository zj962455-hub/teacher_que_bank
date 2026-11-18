#!/usr/bin/env python3
"""阿里云短信认证 · 独立冒烟测试（lesson-39）

不连数据库、不依赖本项目代码，直接调阿里云 SDK。
目的：把「AK 权限 / 签名 / 模板 / 产品是否开通」这四件容易混在一起的事一次分清。

凭据两种来源（跟后端 sms.py 保持一致）：
- app.env 里填了 ALIYUN_SMS_ACCESS_KEY_ID / _SECRET  -> 用静态 AK
- 没填 -> 自动走 ECS 实例 RAM 角色，拿 STS 临时凭据（服务器上不存密钥）

用法（在服务器上，用后端 venv 的 python）：

    # 1. 发一条验证码（脚本自己找 /etc/teacherbank/app.env）
    /opt/teacher-bank/.venv/bin/python deploy/teacher-bank/sms-smoke-test.py send 13800138000

    # 2. 拿收到的验证码核验
    /opt/teacher-bank/.venv/bin/python deploy/teacher-bank/sms-smoke-test.py check 13800138000 123456

注意：本脚本不会打印 AccessKey Secret。
"""

from __future__ import annotations

import json
import os
import sys
from typing import Optional, Tuple

ENV_AK = "ALIYUN_SMS_ACCESS_KEY_ID"
ENV_SECRET = "ALIYUN_SMS_ACCESS_KEY_SECRET"
ENV_SIGN = "ALIYUN_SMS_SIGN_NAME"
ENV_TEMPLATE_CODE = "ALIYUN_SMS_TEMPLATE_CODE"
ENV_TEMPLATE_PARAM = "ALIYUN_SMS_TEMPLATE_PARAM"
ENV_ENDPOINT = "ALIYUN_SMS_ENDPOINT"
ENV_SCHEME = "ALIYUN_SMS_SCHEME_NAME"

DEFAULT_ENDPOINT = "dypnsapi.aliyuncs.com"
DEFAULT_TEMPLATE_PARAM = {"code": "##code##", "min": "5"}

# 与 backend/app/services/sms.py 保持一致
CODE_LENGTH = 6
CODE_VALID_SECONDS = 300
RESEND_INTERVAL_SECONDS = 60

CRED_SOURCE_ENV = "env-ak"
CRED_SOURCE_ECS_ROLE = "ecs-ram-role"

# 阿里云错误码 → 排查方向（都是控制台那边能改的）
DIAGNOSIS = {
    "isv.RAM_PERMISSION_DENY": "RAM 用户没授这两个 action：dypns:SendSmsVerifyCode + dypns:CheckSmsVerifyCode",
    "isp.RAM_PERMISSION_DENY": "RAM 用户没授这两个 action：dypns:SendSmsVerifyCode + dypns:CheckSmsVerifyCode",
    # 实例 RAM 角色没挂上策略时，阿里云回的就是这个
    "Forbidden.NoPermission": "RAM 角色没拿到 dypns 权限：角色详情 → 权限管理 里确认策略已挂上（ram-policy.sms.json 的内容）",
    "Forbidden": "RAM 角色没拿到 dypns 权限：角色详情 → 权限管理 里确认策略已挂上",
    "NoPermission": "RAM 角色没拿到 dypns 权限：角色详情 → 权限管理 里确认策略已挂上",
    "isv.PRODUCT_UNSUBSCRIBE": "短信认证服务没开通（号码认证控制台 → 开通）",
    "isv.PRODUCT_UN_SUBSCRIPT": "短信认证服务没开通（号码认证控制台 → 开通）",
    "isv.SMS_SIGN_ILLEGAL": "签名不合法：检查 ALIYUN_SMS_SIGN_NAME 是否等于赠送签名的 SignName",
    "isv.SIGN_NAME_ILLEGAL": "签名不合法：检查 ALIYUN_SMS_SIGN_NAME 是否等于赠送签名的 SignName",
    "isv.TEMPLATE_ILLEGAL": "模板不合法：检查 ALIYUN_SMS_TEMPLATE_CODE 是否等于赠送模板的 TemplateCode",
    "isv.TEMPLATE_PARAMS_ILLEGAL": "模板参数与模板变量对不上：先清空 ALIYUN_SMS_TEMPLATE_PARAM 用默认值",
    "isv.MOBILE_NUMBER_ILLEGAL": "手机号格式不对",
    "isv.OUT_OF_SERVICE": "账号欠费或服务停用",
    "isv.ACCOUNT_ABNORMAL": "账号状态异常",
    "isv.BUSINESS_LIMIT_CONTROL": "账号级流控（发太猛了，等会儿再试）",
    "isv.SMS_FREQUENCY_LIMIT": "同号频率超限（60 秒内只能发 1 条）",
    "isp.QPS_LIMIT": "请求太频繁",
    "InvalidAccessKeyId.NotFound": "AK 不存在：检查 ALIYUN_SMS_ACCESS_KEY_ID 是否填错/已禁用",
    "InvalidAccessKeySecret.NotFound": "AK 与 SK 不匹配",
    "SignatureDoesNotMatch": "AK/SK 不匹配（也可能是复制时带了空格）",
    "Forbidden": "权限不足：确认 RAM 角色有那两个 action 的授权",
    "Throttling": "被限流了，等几秒重试",
}


def _load_env_file() -> None:
    """没显式设置环境变量时，去读服务器上的 app.env。"""
    if os.getenv(ENV_AK) and os.getenv(ENV_SECRET):
        return
    for path in ("/etc/teacherbank/app.env", "./app.env"):
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip("'").strip('"')
                    if key and value and key not in os.environ:
                        os.environ[key] = value
            print(f"[env] 已从 {path} 载入配置")
            return
        except OSError as exc:
            print(f"[env] 读 {path} 失败: {exc}")


def _static_credentials() -> Optional[Tuple[str, str, str, str]]:
    ak = (os.getenv(ENV_AK) or "").strip()
    sk = (os.getenv(ENV_SECRET) or "").strip()
    if ak and sk:
        return CRED_SOURCE_ENV, ak, sk, ""
    return None


def _role_credentials() -> Optional[Tuple[str, str, str, str]]:
    """ECS 实例 RAM 角色 -> STS 临时凭据。"""
    try:
        from alibabacloud_credentials.client import Client as CredentialClient
        from alibabacloud_credentials.models import Config as CredentialConfig
    except ImportError as exc:
        print(f"[cred] 凭据 SDK 没装: {exc}")
        return None

    try:
        # ⚠️ 超时单位是**毫秒**（SDK 默认 1000ms）。写成 3 会被当成 3ms，
        #    元数据还没应答就超时了。
        client = CredentialClient(
            CredentialConfig(type="ecs_ram_role", connect_timeout=2000, timeout=3000)
        )
        cred = client.get_credential()
    except Exception as exc:
        print(f"[cred] 取实例 RAM 角色失败: {type(exc).__name__}: {exc}")
        return None

    return (
        CRED_SOURCE_ECS_ROLE,
        cred.access_key_id,
        cred.access_key_secret,
        cred.security_token or "",
    )


def _resolve_credentials():
    return _static_credentials() or _role_credentials()


def _missing() -> list[str]:
    """签名和模板是必须的；凭据二选一（静态 AK 或实例 RAM 角色）。"""
    needed = {
        ENV_SIGN: os.getenv(ENV_SIGN),
        ENV_TEMPLATE_CODE: os.getenv(ENV_TEMPLATE_CODE),
    }
    return [k for k, v in needed.items() if not v]


def _client():
    from alibabacloud_dypnsapi20170525.client import Client
    from alibabacloud_tea_openapi import models as open_api_models

    resolved = _resolve_credentials()
    if resolved is None:
        raise RuntimeError(
            "没有可用凭据：app.env 里没填 AK，也没给这台 ECS 绑实例 RAM 角色"
        )

    source, ak, sk, token = resolved
    config = open_api_models.Config(access_key_id=ak, access_key_secret=sk)
    if token:
        config.security_token = token
    config.endpoint = os.getenv(ENV_ENDPOINT) or DEFAULT_ENDPOINT
    print(f"[cred] 凭据来源: {source}")
    return Client(config)


def _fail(exc: Exception) -> int:
    code = getattr(exc, "code", "") or ""
    message = getattr(exc, "message", "") or str(exc)
    data = getattr(exc, "data", {}) or {}
    rid = data.get("RequestId") if isinstance(data, dict) else None

    print("\n❌ 失败")
    print(f"   错误码 : {code or '(空)'}")
    print(f"   报错   : {message}")
    if rid:
        print(f"   RequestId: {rid}")
    hint = DIAGNOSIS.get(code)
    if hint:
        print(f"   排查   : {hint}")
    else:
        print("   排查   : 错误码没在脚本的对照表里，按原文去阿里云文档搜")
    return 1


def do_send(phone: str) -> int:
    from alibabacloud_dypnsapi20170525 import models as dypnsapi_models

    request = dypnsapi_models.SendSmsVerifyCodeRequest()
    request.phone_number = phone
    request.sign_name = os.getenv(ENV_SIGN)
    request.template_code = os.getenv(ENV_TEMPLATE_CODE)
    request.country_code = "86"
    raw_param = os.getenv(ENV_TEMPLATE_PARAM)
    request.template_param = raw_param if raw_param else json.dumps(DEFAULT_TEMPLATE_PARAM)
    request.code_length = CODE_LENGTH
    request.code_type = 1
    request.valid_time = CODE_VALID_SECONDS
    request.interval = RESEND_INTERVAL_SECONDS
    request.duplicate_policy = 1
    request.return_verify_code = False   # 不回传明文码，和线上行为一致
    request.auto_retry = 1
    scheme = os.getenv(ENV_SCHEME)
    if scheme:
        request.scheme_name = scheme

    try:
        response = _client().send_sms_verify_code(request)
    except Exception as exc:
        return _fail(exc)

    body = getattr(response, "body", None)
    ok = bool(getattr(body, "success", False))
    print("\n" + ("✅ 发送成功" if ok else "❌ 发送失败"))
    print(f"   业务状态 : {getattr(body, 'code', '')} {getattr(body, 'message', '')}")
    print(f"   RequestId: {getattr(body, 'request_id', '')}")
    if ok:
        print(f"   手机 {phone} 应该收到一条 {CODE_LENGTH} 位验证码，有效期 {CODE_VALID_SECONDS // 60} 分钟")
        print("   接着核验：")
        print(f"     ... sms-smoke-test.py check {phone} <收到的验证码>")
    return 0 if ok else 1


def do_check(phone: str, code: str) -> int:
    from alibabacloud_dypnsapi20170525 import models as dypnsapi_models

    request = dypnsapi_models.CheckSmsVerifyCodeRequest()
    request.phone_number = phone
    request.verify_code = code
    request.country_code = "86"
    request.case_auth_policy = 1
    scheme = os.getenv(ENV_SCHEME)
    if scheme:
        request.scheme_name = scheme

    try:
        response = _client().check_sms_verify_code(request)
    except Exception as exc:
        return _fail(exc)

    body = getattr(response, "body", None)
    model = getattr(body, "model", None)
    result = getattr(model, "verify_result", "")
    passed = result == "PASS"
    print("\n" + ("✅ 核验通过" if passed else "❌ 核验不通过"))
    print(f"   阿里云返回 : {result or '(空)'}")
    print(f"   业务状态   : {getattr(body, 'code', '')} {getattr(body, 'message', '')}")
    if not passed:
        print("   排查       : 码输错了 / 已过期 / 不是这个手机号收到的 / 60 秒内重复发送后旧码失效")
    return 0 if passed else 1


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2

    mode = argv[1]
    _load_env_file()

    missing = _missing()
    if missing:
        print("❌ 配置不全，缺这些（只报名字，不打印值）：")
        for name in missing:
            print(f"   - {name}")
        print("\n签名和模板填进服务器 /etc/teacherbank/app.env（chmod 600）后重跑。")
        print("（凭据不用填 —— 有静态 AK 就用，没有就自动走实例 RAM 角色）")
        return 2

    if mode == "send":
        if len(argv) != 3:
            print("用法: sms-smoke-test.py send <手机号>")
            return 2
        return do_send(argv[2].strip())

    if mode == "check":
        if len(argv) != 4:
            print("用法: sms-smoke-test.py check <手机号> <验证码>")
            return 2
        return do_check(argv[2].strip(), argv[3].strip())

    print(f"未知模式: {mode}")
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
