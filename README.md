# 每日收盘复盘（云端部署包）

这是一个静态网页。`update_data.py` 会读取公开日线数据并生成 `data.js`；GitHub Actions 在交易日北京时间 15:37 自动更新并发布网页。

## 第一次部署

1. 在 GitHub 新建仓库，例如 `daily-stock-review`。
2. 将本文件夹内的全部内容上传到仓库根目录，包括隐藏的 `.github` 文件夹。
3. 打开仓库 `Settings → Pages`，在 `Build and deployment → Source` 中选择 `GitHub Actions`。
4. 打开 `Actions`，选择 `Update and publish daily review`，点击 `Run workflow`。
5. 成功后，网址通常为 `https://你的用户名.github.io/daily-stock-review/`。

## 隐私说明

- 免费 GitHub Pages 通常要求公开仓库，因此观察清单、网页代码和技术结论会公开。
- 网页中的“我的补充记录”只保存在当前浏览器的 `localStorage`，不会写入仓库。
- 不要把账户号码、身份证、交易密码或其他敏感信息写进网页源文件或提交到 GitHub。

## 更新规则

- 自动时间：交易日北京时间 15:37。
- 也可以在 GitHub 的 `Actions` 页面手动运行。
- GitHub 定时任务可能因平台繁忙而延迟，因此网页必须显示行情日期，不能只看生成时间。

