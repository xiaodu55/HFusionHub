-- 对话图片输入（实验特性, Python 端 CHAT_MULTIMODAL_INPUT_ENABLED 门控）
-- 用户消息可附带最多 4 张图片; images 存相对 URL 的 JSON 数组
-- (如 ["/api/conversation/chat-image/<uuid>.png"]),
-- 图片文件本体在应用本地 app.chat-image-dir 目录,
-- 前端经 GET /conversation/chat-image/{name}(fetch+blob 携带登录态)回源显示。
ALTER TABLE message
    ADD COLUMN images TEXT NULL COMMENT '用户消息附带图片的相对URL JSON数组(V84)';
