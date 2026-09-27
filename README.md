# gofile intake

gofile.io のリンクを渡すとダウンロードしてZIP化し、ブラウザからダウンロードできるWebアプリ。

## ローカルで動かす

```bash
pip install -r requirements.txt
python app.py
```

`http://127.0.0.1:5000` を開く。

## Renderに無料でデプロイする(常時公開したい場合)

1. このフォルダをGitHubリポジトリにpushする
2. https://render.com にサインアップ(クレジットカード不要)
3. 「New +」→「Web Service」→ 先ほどのリポジトリを選択
4. 設定:
   - Environment: `Python 3`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app --workers 1 --threads 8 --timeout 120 --bind 0.0.0.0:$PORT`
     (`Procfile` があるので通常は自動で入る)
   - Instance Type: `Free`
5. Deployを押すと数分で `https://<アプリ名>.onrender.com` のようなURLが発行される

### 無料プランの制約(重要)

- 15分アクセスがないとスリープする。次のアクセス時に起動するまで1分弱かかる
- メモリ512MB・CPU0.1コアと控えめ
- 月750時間まで無料(個人利用なら基本的に足りる)

「いつでも一瞬で開きたい」場合は有料プラン(Starterプラン、月$7〜)でスリープを無効化する必要がある。

### ジョブ管理の仕組み

サーバーはメモリ上でジョブの状態を管理しているため、Start Commandの `--workers 1` は変更しないこと
(workerを増やすと、別プロセスがジョブの状態を見失う)。

完成したZIPはサーバーの一時フォルダに保存され、ダウンロードされなくても2時間経つと自動的に削除される。
