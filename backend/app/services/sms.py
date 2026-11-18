"""短信验证码服务 — lesson-39（阿里云短信认证服务）

用的是阿里云**短信认证服务**（号码认证服务 pnvs 下的「短信认证」原子能力），
不是通用短信服务（DMS）。差别就三条：

- 免申请资质、签名、模板 —— 控制台开一下就有，用赠送签名 + 赠送模板
- 核验免费，只有发送按条计费（0.06 元/条起，量越大越便宜）
- 落款是**阿里云赠送的签名**，不是自己的品牌（老大 2026-11-18 拍板先这样）

验证码由阿里云生成并保管
-----------------------
发送时 TemplateParam 传 {"code": "##code##", "min": "5"}：
「##code##」是占位符 —— 阿里云自己生成 6 位数字码并**存在它那边**，
我们全程不知道明文验证码。核验时调 CheckSmsVerifyCode，由阿里云比对它存的那份。

所以本地库里没有验证码可偷（表里只记「给哪个号发过、结果如何」）。
代价是核验必须走一次网络往返 —— 本来就是网络场景，可以接受。

频控
----
全项目没有限流中间件，这里自己兜住（0.06 元/条，被刷一次就是几十块）：

- 同号 60 秒 1 条、每天最多 10 条
- 同 IP 每小时最多 20 条、每天最多 100 条
- 同号核验失败每小时最多 10 次（6 位码 5 分钟内穷举不完）

失败时给老师的文案
------------------
每个阿里云错误码配一句人话 + 一个机器码 —— 老师才知道该等、该重输，还是该找管理员。
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlmodel import Session, select

from app.models import SmsAttempt
from app.services.errors import (
    CODE_SMS_CODE_INVALID,
    CODE_SMS_NOT_CONFIGURED,
    CODE_SMS_RATE_LIMITED,
    CODE_SMS_SEND_FAILED,
    CODE_VALIDATION,
    ApiHTTPException,
)


# ============ 配置（全部来自环境变量）============
# 线上是 /etc/teacherbank/app.env（600 权限，不入 git），
# 老大填 AK 时就改那个文件，不用动代码。

ENV_AK = "ALIYUN_SMS_ACCESS_KEY_ID"
ENV_SECRET = "ALIYUN_SMS_ACCESS_KEY_SECRET"
ENV_SIGN = "ALIYUN_SMS_SIGN_NAME"
ENV_TEMPLATE_CODE = "ALIYUN_SMS_TEMPLATE_CODE"
ENV_TEMPLATE_PARAM = "ALIYUN_SMS_TEMPLATE_PARAM"
ENV_ENDPOINT = "ALIYUN_SMS_ENDPOINT"
ENV_SCHEME = "ALIYUN_SMS_SCHEME_NAME"

DEFAULT_ENDPOINT = "dypnsapi.aliyuncs.com"

# 默认模板参数：##code## = 让阿里云生成验证码（我们看不到明文）
# min 是模板里「有效期」那个变量的值（分钟）
DEFAULT_TEMPLATE_PARAM = {"code": "##code##", "min": "5"}


# ============ 凭据：静态 AK 或 ECS 实例 RAM 角色（STS）============
# 优先用 env 里的静态 AK（老配置、别的机器也能跑）；
# 没有就自动走 ECS 实例 RAM 角色 —— 拿 STS 临时凭据，服务器上根本不存密钥。
#
# 线上这台是阿里云 ECS（i-0jldm8ubd3nmhp5b5e8tZ / cn-wulanchabu），
# 绑了实例 RAM 角色之后，app.env 里两个 AK 变量可以完全不填。

CRED_SOURCE_ENV = "env-ak"
CRED_SOURCE_ECS_ROLE = "ecs-ram-role"
CRED_SOURCE_NONE = "none"

# 取到凭据后的缓存时长。远小于 STS 令牌寿命（≥1 小时），
# 目的是别让每个请求都去戳一次元数据服务。
_CRED_OK_TTL = 60.0
# 取不到时的负缓存：连不上元数据时别把每个请求都拖慢
_CRED_FAIL_TTL = 10.0

_cred_cache = None
_cred_cache_at = 0.0
_cred_fail_until = 0.0

# SDK 的凭据客户端只创建一次：
# EcsRamRoleCredential 继承了 _AutomaticallyRefreshCredentials，
# STS 令牌过期时 SDK 自己会续期 —— 所以缓存「客户端」而不是「令牌」。
_credential_client = None


class SmsCredentialError(RuntimeError):
    """拿不到阿里云凭据（既没配 AK，也没绑实例 RAM 角色）。"""


def _static_credentials():
    """env 里的静态 AK。返回 (来源, ak, sk, token) 或 None。"""
    ak = (os.getenv(ENV_AK) or "").strip()
    sk = (os.getenv(ENV_SECRET) or "").strip()
    if ak and sk:
        return CRED_SOURCE_ENV, ak, sk, ""
    return None


def _ecs_role_credentials():
    """从 ECS 实例 RAM 角色取 STS 临时凭据。

    服务器上不需要存任何密钥 —— 凭据由元数据服务（100.100.100.200）发放，
    控制台给实例绑上 RAM 角色之后自动生效。
    """
    from alibabacloud_credentials.client import Client as CredentialClient
    from alibabacloud_credentials.models import Config as CredentialConfig

    global _credential_client
    if _credential_client is None:
        # ⚠️ 超时单位是**毫秒**（SDK 默认 1000ms，Tea 的 readTimeout 也按 ms 解释）。
        #    写成 3 会被当成 3ms，报错里显示 read timeout=0.003 秒 ——
        #    那样元数据还没应答就超时了，绑了角色也永远拿不到凭据。
        _credential_client = CredentialClient(
            CredentialConfig(type="ecs_ram_role", connect_timeout=2000, timeout=3000)
        )
    cred = _credential_client.get_credential()
    return (
        CRED_SOURCE_ECS_ROLE,
        cred.access_key_id,
        cred.access_key_secret,
        cred.security_token or "",
    )


def _resolve_credentials():
    """解析当前该用哪份凭据。返回 (来源, ak, sk, token) 或 None。"""
    global _cred_cache, _cred_cache_at, _cred_fail_until

    static = _static_credentials()
    if static:
        return static

    now = time.monotonic()

    # 刚失败过就先别重复戳元数据服务
    if now < _cred_fail_until:
        return None

    if _cred_cache is not None and (now - _cred_cache_at) < _CRED_OK_TTL:
        return _cred_cache

    try:
        resolved = _ecs_role_credentials()
    except Exception:
        resolved = None

    if resolved is None:
        _cred_fail_until = now + _CRED_FAIL_TTL
        _cred_cache = None
    else:
        _cred_cache = resolved
        _cred_cache_at = now
    return resolved


def credential_source() -> str:
    """当前凭据来源：env-ak / ecs-ram-role / none（排查用）。"""
    resolved = _resolve_credentials()
    return resolved[0] if resolved else CRED_SOURCE_NONE


# ============ 频控阈值 ============

# 同号最短间隔（秒）—— 和发给阿里云的 Interval 参数保持一致
RESEND_INTERVAL_SECONDS = 60
# 同号每天上限
PHONE_DAILY_LIMIT = 10
# 同 IP 每小时上限
IP_HOURLY_LIMIT = 20
# 同 IP 每天上限
IP_DAILY_LIMIT = 100
# 同号每小时核验失败上限（防穷举 6 位码）
VERIFY_FAIL_HOURLY_LIMIT = 10

# 验证码位数与有效期（阿里云侧限制：4-8 位，默认 4）
CODE_LENGTH = 6
CODE_VALID_SECONDS = 300


# 阿里云错误码 → (给老师的文案, 机器码)
_ERROR_MAP = {
    "isv.PRODUCT_UNSUBSCRIBE": ("短信服务还没开通，请联系管理员", CODE_SMS_NOT_CONFIGURED),
    "isv.PRODUCT_UN_SUBSCRIPT": ("短信服务还没开通，请联系管理员", CODE_SMS_NOT_CONFIGURED),
    "isv.RAM_PERMISSION_DENY": ("短信服务权限没配好，请联系管理员", CODE_SMS_NOT_CONFIGURED),
    "isp.RAM_PERMISSION_DENY": ("短信服务权限没配好，请联系管理员", CODE_SMS_NOT_CONFIGURED),
    # RAM 角色没授到 dypns 权限时，阿里云回的是 Forbidden.NoPermission（不是 isv.*）
    "Forbidden.NoPermission": ("短信服务权限没配好，请联系管理员", CODE_SMS_NOT_CONFIGURED),
    "Forbidden": ("短信服务权限没配好，请联系管理员", CODE_SMS_NOT_CONFIGURED),
    "NoPermission": ("短信服务权限没配好，请联系管理员", CODE_SMS_NOT_CONFIGURED),
    "isv.OUT_OF_SERVICE": ("短信服务欠费了，请联系管理员", CODE_SMS_SEND_FAILED),
    "isv.ACCOUNT_ABNORMAL": ("短信服务账号状态异常，请联系管理员", CODE_SMS_SEND_FAILED),
    "isp.QPS_LIMIT": ("请求太频繁了，请稍后再试", CODE_SMS_RATE_LIMITED),
    "isv.MOBILE_NUMBER_ILLEGAL": ("手机号格式不对，检查一下", CODE_VALIDATION),
    "isv.INVALID_PARAMETERS": ("短信参数不对，请联系管理员", CODE_SMS_SEND_FAILED),
}


def is_configured() -> bool:
    """短信服务是否配齐了（凭据 + 签名 + 模板）。

    少任何一个都不能发码 —— 这时候应该报「找管理员」，
    而不是让老师对着一个永远失败的按钮发呆。

    凭据可以是静态 AK，也可以是 ECS 实例 RAM 角色发的 STS 临时凭据
    （绑了实例角色之后，app.env 里两个 AK 变量可以不填）。
    """
    if not (os.getenv(ENV_SIGN) and os.getenv(ENV_TEMPLATE_CODE)):
        return False
    return _resolve_credentials() is not None


def normalize_phone(raw: str) -> str:
    """把老师可能输入的 138-0013-8000 / 138 0013 8000 规整成纯数字。

    也顺手去掉国际区号 +86 / 0086 —— 有人会照着别处的习惯写。
    """
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    if len(digits) == 13 and digits.startswith("86"):
        digits = digits[2:]
    elif len(digits) == 14 and digits.startswith("0086"):
        digits = digits[4:]
    return digits


def mask_phone(phone: str) -> str:
    """手机号打码（138****8000）—— 出现在同事能看到的列表里。"""
    p = normalize_phone(phone)
    if len(p) != 11:
        return "***"
    return p[:3] + "****" + p[-4:]


def _client():
    """构造阿里云客户端（惰性 —— 没凭据时 import 也不炸）。

    凭据两种来源：
    - env 里的静态 AK
    - ECS 实例 RAM 角色发的 STS 临时凭据（推荐，服务器不存密钥）
    """
    from alibabacloud_dypnsapi20170525.client import Client
    from alibabacloud_tea_openapi import models as open_api_models

    resolved = _resolve_credentials()
    if resolved is None:
        raise SmsCredentialError(
            "没有可用的阿里云凭据：app.env 里没填 AK，也没给这台 ECS 绑实例 RAM 角色"
        )

    _source, ak, sk, token = resolved
    config = open_api_models.Config(
        access_key_id=ak,
        access_key_secret=sk,
    )
    if token:
        # STS 临时凭据必须带上 token 一起签名
        config.security_token = token
    config.endpoint = os.getenv(ENV_ENDPOINT) or DEFAULT_ENDPOINT
    return Client(config)


def _translate_error(exc: Exception) -> ApiHTTPException:
    """阿里云异常 → 统一错误契约（人话 + 机器码）。

    异常对象上取 code / message —— SDK 两种异常基类字段名一致，
    所以不用 import 具体的异常类（换个 SDK 版本也不会炸）。
    """
    if isinstance(exc, SmsCredentialError):
        return ApiHTTPException(
            status_code=503,
            detail="短信服务凭据没配好，请联系管理员",
            code=CODE_SMS_NOT_CONFIGURED,
        )

    code = getattr(exc, "code", "") or ""
    message = getattr(exc, "message", "") or str(exc)

    if code in _ERROR_MAP:
        detail, machine = _ERROR_MAP[code]
        return ApiHTTPException(status_code=400, detail=detail, code=machine)

    # 没见过的错误码：带上阿里云原文，排查时能搜到
    return ApiHTTPException(
        status_code=503,
        detail=f"短信服务出错了：{message}",
        code=CODE_SMS_SEND_FAILED,
    )


def _log_attempt(session: Session, phone: str, ip: str, action: str, ok: bool) -> None:
    """记一条流水（频控 + 审计 + 投诉溯源）。"""
    session.add(
        SmsAttempt(phone=phone[:20], ip=(ip or "")[:45], action=action, ok=ok)
    )
    session.commit()


def send_code(session: Session, phone: str, ip: str = "") -> None:
    """发一条验证码短信。失败直接抛 ApiHTTPException（统一契约）。

    频控在发之前查流水表 —— 拦在阿里云之前，一分钱都不花。
    """
    if not is_configured():
        raise ApiHTTPException(
            status_code=503,
            detail="短信服务还没开通，请联系管理员",
            code=CODE_SMS_NOT_CONFIGURED,
        )

    phone = normalize_phone(phone)
    if len(phone) != 11 or not phone.startswith("1"):
        raise ApiHTTPException(
            status_code=400,
            detail="手机号格式不对，检查一下",
            code=CODE_VALIDATION,
        )

    now = datetime.now(timezone.utc)

    # 同号 60 秒 1 条
    recent = session.exec(
        select(SmsAttempt).where(
            SmsAttempt.phone == phone,
            SmsAttempt.action == "send",
            SmsAttempt.created_at >= now - timedelta(seconds=RESEND_INTERVAL_SECONDS),
        )
    ).first()
    if recent is not None:
        raise ApiHTTPException(
            status_code=429,
            detail=f"刚发过验证码，{RESEND_INTERVAL_SECONDS} 秒后再试",
            code=CODE_SMS_RATE_LIMITED,
        )

    # 同号每天上限
    today_phone = session.exec(
        select(SmsAttempt).where(
            SmsAttempt.phone == phone,
            SmsAttempt.action == "send",
            SmsAttempt.created_at >= now - timedelta(days=1),
        )
    ).all()
    if len(today_phone) >= PHONE_DAILY_LIMIT:
        raise ApiHTTPException(
            status_code=429,
            detail="今天发得太多了，明天再试",
            code=CODE_SMS_RATE_LIMITED,
        )

    # 同 IP 每小时上限
    if ip:
        hour_ip = session.exec(
            select(SmsAttempt).where(
                SmsAttempt.ip == ip,
                SmsAttempt.action == "send",
                SmsAttempt.created_at >= now - timedelta(hours=1),
            )
        ).all()
        if len(hour_ip) >= IP_HOURLY_LIMIT:
            raise ApiHTTPException(
                status_code=429,
                detail="发得太频繁了，请一小时后再试",
                code=CODE_SMS_RATE_LIMITED,
            )

        # 同 IP 每天上限
        day_ip = session.exec(
            select(SmsAttempt).where(
                SmsAttempt.ip == ip,
                SmsAttempt.action == "send",
                SmsAttempt.created_at >= now - timedelta(days=1),
            )
        ).all()
        if len(day_ip) >= IP_DAILY_LIMIT:
            raise ApiHTTPException(
                status_code=429,
                detail="今天发得太多了，明天再试",
                code=CODE_SMS_RATE_LIMITED,
            )

    # ===== 真发 =====
    from alibabacloud_dypnsapi20170525 import models as dypnsapi_models

    request = dypnsapi_models.SendSmsVerifyCodeRequest()
    request.phone_number = phone
    request.sign_name = os.getenv(ENV_SIGN)
    request.template_code = os.getenv(ENV_TEMPLATE_CODE)
    request.country_code = "86"
    # 「##code##」= 阿里云自己生成并保存验证码（我们看不到明文）
    raw_param = os.getenv(ENV_TEMPLATE_PARAM)
    template_param = raw_param if raw_param else json.dumps(DEFAULT_TEMPLATE_PARAM)
    request.template_param = template_param
    request.code_length = CODE_LENGTH
    request.code_type = 1
    request.valid_time = CODE_VALID_SECONDS
    request.interval = RESEND_INTERVAL_SECONDS
    request.duplicate_policy = 1
    request.return_verify_code = False
    request.auto_retry = 1
    scheme = os.getenv(ENV_SCHEME)
    if scheme:
        request.scheme_name = scheme

    try:
        response = _client().send_sms_verify_code(request)
    except Exception as exc:
        _log_attempt(session, phone, ip, "send", False)
        raise _translate_error(exc) from exc

    body = getattr(response, "body", None)
    ok = bool(getattr(body, "success", False))
    _log_attempt(session, phone, ip, "send", ok)

    if not ok:
        raise ApiHTTPException(
            status_code=503,
            detail="短信没发出去，请稍后再试",
            code=CODE_SMS_SEND_FAILED,
        )


def verify_code(session: Session, phone: str, code: str, ip: str = "") -> None:
    """核验验证码。通过就静默返回，不通过抛 ApiHTTPException。

    核验在阿里云那边做（我们没有明文码可比对）。
    """
    if not is_configured():
        raise ApiHTTPException(
            status_code=503,
            detail="短信服务还没开通，请联系管理员",
            code=CODE_SMS_NOT_CONFIGURED,
        )

    phone = normalize_phone(phone)
    code = (code or "").strip()
    if len(phone) != 11 or not phone.startswith("1"):
        raise ApiHTTPException(
            status_code=400,
            detail="手机号格式不对，检查一下",
            code=CODE_VALIDATION,
        )
    # 格式都不对就别浪费一次网络往返
    if not code.isdigit() or len(code) != CODE_LENGTH:
        raise ApiHTTPException(
            status_code=400,
            detail=f"验证码是 {CODE_LENGTH} 位数字",
            code=CODE_SMS_CODE_INVALID,
        )

    now = datetime.now(timezone.utc)

    # 同号每小时核验失败上限（防穷举 6 位码）
    fails = session.exec(
        select(SmsAttempt).where(
            SmsAttempt.phone == phone,
            SmsAttempt.action == "verify",
            SmsAttempt.ok == False,  # noqa: E712
            SmsAttempt.created_at >= now - timedelta(hours=1),
        )
    ).all()
    if len(fails) >= VERIFY_FAIL_HOURLY_LIMIT:
        raise ApiHTTPException(
            status_code=429,
            detail="验证码错误次数太多，请一小时后再试",
            code=CODE_SMS_RATE_LIMITED,
        )

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
        _log_attempt(session, phone, ip, "verify", False)
        raise _translate_error(exc) from exc

    model = getattr(getattr(response, "body", None), "model", None)
    passed = getattr(model, "verify_result", "") == "PASS"
    _log_attempt(session, phone, ip, "verify", passed)

    if not passed:
        raise ApiHTTPException(
            status_code=400,
            detail="验证码不对或已过期，重新输一下",
            code=CODE_SMS_CODE_INVALID,
        )


def mask_for_display(phone: Optional[str]) -> str:
    """给前端用的打码手机号（空值返回空串）。"""
    if not phone:
        return ""
    return mask_phone(phone)