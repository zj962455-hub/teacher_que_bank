# SSH 密钥配置指南

> 一把 ed25519 密钥搞定 GitHub + 阿里云 ECS,比 PAT 更省事。

---

## ✅ 已完成(老大不用做)

- ✅ SSH 密钥已生成: `~/.ssh/id_ed25519` (私钥) + `~/.ssh/id_ed25519.pub` (公钥)
- ✅ 已加到 macOS ssh-agent + Keychain (开机自动加载)
- ✅ `~/.ssh/config` 已配置 `github.com` 和 `ecs` 两个 Host 别名

---

## 🎯 老大你要做的(2 件事)

### 1. 公钥贴到 GitHub(以后 push 不用输密码)

**步骤**:
1. 打开 <https://github.com/settings/keys>
2. 点右上角 **"New SSH key"**
3. 填:
   - **Title**: `rrobot-Mac-mini` (随便起,自己能认出就行)
   - **Key type**: Authentication Key
   - **Key**: 粘贴下面这串 ↓
4. 点 **"Add SSH key"**
5. 输 GitHub 密码确认

**公钥**(整行,包含 `ssh-ed25519` 开头到结尾):

```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIL+L0gzQlNW3KQjfDddlBG+bM92tAy9avPxxyUXQ72Sl rrobot@teacher-question-bank
```

或者用命令复制到剪贴板(以后再要):

```bash
pbcopy < ~/.ssh/id_ed25519.pub
echo "已复制到剪贴板"
```

---

### 2. 公钥贴到阿里云 ECS(以后 SSH 不用输密码)

**步骤**:
1. 打开阿里云 ECS 控制台 <https://ecs.console.aliyun.com/>
2. 找到你的实例 → 点 **"远程连接"** → **"Workbench 远程连接"**
3. 首次会让你设一个 6 位 **会话密码**(随便设,后面用这个登)
4. 连上后,在终端里执行:

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIL+L0gzQlNW3KQjfDddlBG+bM92tAy9avPxxyUXQ72Sl rrobot@teacher-question-bank" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
cat ~/.ssh/authorized_keys   # 确认有内容
```

5. 退出 Workbench

---

## ✅ 测试连接

```bash
# 测试 GitHub
ssh -T git@github.com
# 期望: "Hi zj962455-hub! You've successfully authenticated, but GitHub does not provide shell access."

# 测试 ECS
ssh ecs
# 期望: 直接进入 root shell,不需要输密码
# 第一次连会问 "Are you sure you want to continue connecting?" → yes
```

如果都通,你以后可以:

```bash
# 推送代码不用输密码
cd ~/Desktop/dev/teacher_question_bank
git push

# SSH 连 ECS 直接进
ssh ecs
```

---

## 🔧 怎么 SSH 连 ECS (后续常用)

| 命令 | 效果 |
|---|---|
| `ssh ecs` | 用密钥连,直接进 root shell |
| `ssh root@8.160.177.222` | 同上(用 IP) |
| `ssh -p 2222 ecs` | 如果以后改了端口 |
| `scp file.txt ecs:/root/` | 传文件到 ECS |
| `ssh ecs "docker ps"` | 在 ECS 跑命令,不进 shell |

---

## 🆘 卡住怎么办

| 问题 | 解决 |
|---|---|
| `Permission denied (publickey)` | 公钥没贴对位置,检查 `~/.ssh/authorized_keys` 末尾有无换行 |
| Workbench 连不上 | ECS 安全组要放行 22 端口(默认放行,除非你改过) |
| ssh-agent 不认 key | 重新跑 `ssh-add --apple-use-keychain ~/.ssh/id_ed25519` |
| ECS root 登不上 | 可能阿里云默认禁 root,先 Workbench 用 `sudo -i` 切 root |

---

## 📚 备选方案:PAT (Personal Access Token)

如果 SSH 配置实在搞不定(比如 ECS 重装过、GitHub 出 bug),用 HTTPS + PAT:

1. 去 <https://github.com/settings/tokens> 生成 token
2. 选 `repo` 权限 + `workflow`(如果要 CI)
3. 生成后**只显示一次**,复制保存
4. 推代码:
   ```bash
   git remote set-url origin https://<TOKEN>@github.com/zj962455-hub/teacher_que_bank.git
   git push
   ```

但**强烈推荐 SSH 方案**——一次配置,终身免输。

---

**老大把 GitHub + ECS 两处都贴好公钥后告诉我,我帮你测连接 ✅**