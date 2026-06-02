-- ============================================================
-- 海外藏中国文物知识图谱数据库初始化脚本
-- 数据库: seitem
-- ============================================================

CREATE DATABASE IF NOT EXISTS seitem
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE seitem;

-- 1. 博物馆表
CREATE TABLE IF NOT EXISTS museums (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    name VARCHAR(200) NOT NULL COMMENT '博物馆官方完整名称',
    short_name VARCHAR(100) COMMENT '简称',
    country VARCHAR(100) NOT NULL COMMENT '国家',
    city VARCHAR(100) COMMENT '城市',
    website VARCHAR(255) COMMENT '官网URL',
    collection_url VARCHAR(255) COMMENT '藏品搜索URL',
    created_at DATETIME COMMENT '创建时间',
    updated_at DATETIME COMMENT '更新时间'
) COMMENT='博物馆信息';

-- 2. 朝代表
CREATE TABLE IF NOT EXISTS dynasties (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    name_zh VARCHAR(50) NOT NULL COMMENT '中文朝代名称',
    name_en VARCHAR(100) COMMENT '英文名称',
    start_year INT COMMENT '起始年份（公元前为负）',
    end_year INT COMMENT '结束年份',
    description TEXT COMMENT '朝代简介',
    created_at DATETIME COMMENT '创建时间'
) COMMENT='历史朝代';

-- 3. 艺术家表
CREATE TABLE IF NOT EXISTS artists (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    name_zh VARCHAR(100) COMMENT '中文名',
    name_en VARCHAR(200) COMMENT '英文名',
    birth_year INT COMMENT '生年',
    death_year INT COMMENT '卒年',
    dynasty_id INT UNSIGNED COMMENT '主要活跃朝代ID',
    biography TEXT COMMENT '生平介绍',
    baidu_url VARCHAR(255) COMMENT '百度百科链接',
    wiki_url VARCHAR(255) COMMENT '维基百科链接',
    created_at DATETIME COMMENT '创建时间',
    updated_at DATETIME COMMENT '更新时间'
) COMMENT='艺术家（书画家等）';

-- 4. 地点表
CREATE TABLE IF NOT EXISTS locations (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    name_zh VARCHAR(100) NOT NULL COMMENT '中文名称',
    name_en VARCHAR(200) COMMENT '英文名称',
    parent_id INT UNSIGNED COMMENT '上级地点ID',
    type VARCHAR(20) COMMENT '类型：country/province/city/site',
    created_at DATETIME COMMENT '创建时间'
) COMMENT='地理地点';

-- 5. 文物主表
CREATE TABLE IF NOT EXISTS artifacts (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    object_id VARCHAR(100) NOT NULL COMMENT '博物馆原始ID或系统生成唯一标识',
    title_zh VARCHAR(500) COMMENT '中文名称',
    title_en VARCHAR(500) NOT NULL COMMENT '英文原始名称',
    time_period VARCHAR(200) COMMENT '年代描述（原始）',
    dynasty_id INT UNSIGNED COMMENT '所属朝代ID',
    type VARCHAR(100) COMMENT '文物类型（如 Painting, Ceramics）',
    material VARCHAR(200) COMMENT '材质',
    description TEXT COMMENT '文物介绍文本',
    dimensions VARCHAR(200) COMMENT '尺寸',
    museum_id INT UNSIGNED NOT NULL COMMENT '现藏博物馆ID',
    location_id INT UNSIGNED COMMENT '博物馆所在地ID',
    detail_url VARCHAR(500) NOT NULL COMMENT '博物馆详情页URL',
    image_url VARCHAR(500) NOT NULL COMMENT '主图原图URL',
    image_path VARCHAR(500) COMMENT '本地存储相对路径',
    credit_line VARCHAR(300) COMMENT '版权/来源说明',
    accession_number VARCHAR(100) COMMENT '馆藏编号',
    crawl_date DATE NOT NULL COMMENT '爬取日期',
    image_validated TINYINT COMMENT '图片有效性验证 0/1',
    last_updated DATETIME COMMENT '最后更新时间',
    created_at DATETIME COMMENT '创建时间',
    UNIQUE INDEX idx_museum_object (museum_id, object_id)
) COMMENT='文物主表';

-- 6. 文物多图片表
CREATE TABLE IF NOT EXISTS artifact_images (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    artifact_id INT UNSIGNED NOT NULL COMMENT '文物ID',
    image_url VARCHAR(500) NOT NULL COMMENT '图片URL',
    image_path VARCHAR(500) COMMENT '本地存储路径',
    is_primary TINYINT COMMENT '是否主图 0/1',
    sort_order INT COMMENT '排序序号'
) COMMENT='文物多图片';

-- 7. 文物-艺术家关联表
CREATE TABLE IF NOT EXISTS artifact_artist (
    artifact_id INT UNSIGNED NOT NULL COMMENT '文物ID',
    artist_id INT UNSIGNED NOT NULL COMMENT '艺术家ID',
    relationship_type VARCHAR(50) COMMENT '关系类型（creator/collector等）',
    INDEX idx_artifact_artist (artifact_id, artist_id)
) COMMENT='文物与艺术家关联';

-- 8. 文物-地点关联表
CREATE TABLE IF NOT EXISTS artifact_location (
    artifact_id INT UNSIGNED NOT NULL COMMENT '文物ID',
    location_id INT UNSIGNED NOT NULL COMMENT '地点ID',
    role VARCHAR(50) COMMENT '角色（出土地/制作地等）',
    INDEX idx_artifact_location (artifact_id, location_id)
) COMMENT='文物与地点关联';

-- 9. 用户表
CREATE TABLE IF NOT EXISTS users (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    username VARCHAR(50) NOT NULL COMMENT '用户名',
    password_hash VARCHAR(255) NOT NULL COMMENT '密码哈希',
    email VARCHAR(100) COMMENT '邮箱',
    phone VARCHAR(20) COMMENT '手机号',
    avatar_url VARCHAR(500) COMMENT '头像URL',
    nickname VARCHAR(50) COMMENT '昵称',
    status VARCHAR(20) DEFAULT 'active' COMMENT '状态：active/disabled/banned',
    ban_reason TEXT COMMENT '封禁原因',
    registered_at DATETIME COMMENT '注册时间',
    last_login DATETIME COMMENT '最后登录时间',
    last_ip VARCHAR(45) COMMENT '最后登录IP',
    source VARCHAR(20) COMMENT '注册来源：web/app',
    comment_disabled TINYINT DEFAULT 0 COMMENT '是否禁止评论',
    upload_disabled TINYINT DEFAULT 0 COMMENT '是否禁止上传',
    created_at DATETIME COMMENT '创建时间',
    updated_at DATETIME COMMENT '更新时间'
) COMMENT='统一用户表';

-- 10. 角色表
CREATE TABLE IF NOT EXISTS roles (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    name VARCHAR(50) NOT NULL COMMENT '角色标识（super_admin等）',
    display_name VARCHAR(50) NOT NULL COMMENT '显示名称',
    description TEXT COMMENT '描述',
    created_at DATETIME COMMENT '创建时间',
    updated_at DATETIME COMMENT '更新时间'
) COMMENT='角色表';

-- 11. 权限表
CREATE TABLE IF NOT EXISTS permissions (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    name VARCHAR(100) NOT NULL COMMENT '权限标识（artifact:edit）',
    display_name VARCHAR(100) COMMENT '显示名称',
    module VARCHAR(50) COMMENT '所属模块',
    created_at DATETIME COMMENT '创建时间'
) COMMENT='权限表';

-- 12. 角色-权限关联表
CREATE TABLE IF NOT EXISTS role_permissions (
    role_id INT UNSIGNED NOT NULL COMMENT '角色ID',
    permission_id INT UNSIGNED NOT NULL COMMENT '权限ID',
    INDEX idx_role_perm (role_id, permission_id)
) COMMENT='角色权限关联';

-- 13. 用户-角色关联表
CREATE TABLE IF NOT EXISTS user_roles (
    user_id INT UNSIGNED NOT NULL COMMENT '用户ID',
    role_id INT UNSIGNED NOT NULL COMMENT '角色ID',
    granted_by INT UNSIGNED COMMENT '授权人用户ID',
    granted_at DATETIME COMMENT '授权时间'
) COMMENT='用户角色关联';

-- 14. 用户收藏
CREATE TABLE IF NOT EXISTS user_favorites (
    user_id INT UNSIGNED NOT NULL COMMENT '用户ID',
    artifact_id INT UNSIGNED NOT NULL COMMENT '文物ID',
    group_name VARCHAR(50) COMMENT '收藏分组名称',
    created_at DATETIME COMMENT '收藏时间'
) COMMENT='用户收藏文物';

-- 15. 浏览历史
CREATE TABLE IF NOT EXISTS user_browse_history (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    user_id INT UNSIGNED NOT NULL COMMENT '用户ID',
    artifact_id INT UNSIGNED NOT NULL COMMENT '文物ID',
    browse_time DATETIME COMMENT '浏览时间'
) COMMENT='用户浏览历史';

-- 16. 文物点赞
CREATE TABLE IF NOT EXISTS artifact_likes (
    user_id INT UNSIGNED NOT NULL COMMENT '用户ID',
    artifact_id INT UNSIGNED NOT NULL COMMENT '文物ID',
    liked_at DATETIME COMMENT '点赞时间'
) COMMENT='文物点赞';

-- 17. 评论表
CREATE TABLE IF NOT EXISTS user_comments (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    user_id INT UNSIGNED NOT NULL COMMENT '用户ID',
    artifact_id INT UNSIGNED NOT NULL COMMENT '文物ID',
    parent_id INT UNSIGNED COMMENT '父评论ID',
    content TEXT NOT NULL COMMENT '评论内容',
    like_count INT DEFAULT 0 COMMENT '点赞数',
    status VARCHAR(20) DEFAULT 'pending' COMMENT '状态：pending/approved/rejected',
    audit_by INT UNSIGNED COMMENT '审核人ID',
    audit_time DATETIME COMMENT '审核时间',
    reject_reason VARCHAR(200) COMMENT '拒绝原因',
    created_at DATETIME COMMENT '创建时间'
) COMMENT='用户评论';

-- 18. 评论点赞
CREATE TABLE IF NOT EXISTS comment_likes (
    user_id INT UNSIGNED NOT NULL COMMENT '用户ID',
    comment_id INT UNSIGNED NOT NULL COMMENT '评论ID',
    liked_at DATETIME COMMENT '点赞时间'
) COMMENT='评论点赞';

-- 19. 用户上传内容
CREATE TABLE IF NOT EXISTS user_uploads (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    user_id INT UNSIGNED NOT NULL COMMENT '用户ID',
    artifact_id INT UNSIGNED COMMENT '关联文物ID',
    media_type VARCHAR(20) NOT NULL COMMENT '媒体类型：image/audio/video',
    file_url VARCHAR(500) NOT NULL COMMENT '文件URL',
    file_path VARCHAR(500) COMMENT '本地存储路径',
    caption VARCHAR(500) COMMENT '用户描述',
    location_taken VARCHAR(200) COMMENT '拍摄地点',
    status VARCHAR(20) DEFAULT 'pending' COMMENT '审核状态：pending/approved/rejected',
    audit_by INT UNSIGNED COMMENT '审核人ID',
    audit_time DATETIME COMMENT '审核时间',
    reject_reason VARCHAR(200) COMMENT '拒绝原因',
    like_count INT DEFAULT 0 COMMENT '点赞数',
    created_at DATETIME COMMENT '创建时间'
) COMMENT='用户上传内容';

-- 20. 用户动态
CREATE TABLE IF NOT EXISTS user_posts (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    user_id INT UNSIGNED NOT NULL COMMENT '用户ID',
    content TEXT NOT NULL COMMENT '动态内容',
    artifact_id INT UNSIGNED COMMENT '关联文物ID',
    museum_id INT UNSIGNED COMMENT '关联博物馆ID',
    image_urls TEXT COMMENT '图片URL列表（JSON或逗号分隔）',
    like_count INT DEFAULT 0 COMMENT '点赞数',
    comment_count INT DEFAULT 0 COMMENT '评论数',
    status VARCHAR(20) DEFAULT 'pending' COMMENT '审核状态：pending/approved/rejected',
    audit_by INT UNSIGNED COMMENT '审核人ID',
    audit_time DATETIME COMMENT '审核时间',
    reject_reason VARCHAR(200) COMMENT '拒绝原因',
    created_at DATETIME COMMENT '创建时间'
) COMMENT='用户动态';

-- 21. 动态点赞
CREATE TABLE IF NOT EXISTS post_likes (
    user_id INT UNSIGNED NOT NULL COMMENT '用户ID',
    post_id INT UNSIGNED NOT NULL COMMENT '动态ID',
    liked_at DATETIME COMMENT '点赞时间'
) COMMENT='动态点赞';

-- 22. 用户关注
CREATE TABLE IF NOT EXISTS user_follows (
    follower_id INT UNSIGNED NOT NULL COMMENT '关注者用户ID',
    followee_id INT UNSIGNED NOT NULL COMMENT '被关注者用户ID',
    created_at DATETIME COMMENT '关注时间'
) COMMENT='用户关注';

-- 23. 敏感词库
CREATE TABLE IF NOT EXISTS sensitive_words (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    word VARCHAR(100) NOT NULL COMMENT '敏感词',
    category VARCHAR(50) COMMENT '分类：political/pornographic/violence/advertising/other',
    status TINYINT DEFAULT 1 COMMENT '状态：1-启用 0-禁用',
    created_at DATETIME NOT NULL COMMENT '创建时间',
    updated_at DATETIME COMMENT '更新时间',
    INDEX idx_word (word),
    INDEX idx_category (category)
) COMMENT='敏感词库';

-- 24. 爬取任务记录
CREATE TABLE IF NOT EXISTS crawl_tasks (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    museum_id INT UNSIGNED NOT NULL COMMENT '博物馆ID',
    start_time DATETIME NOT NULL COMMENT '开始时间',
    end_time DATETIME COMMENT '结束时间',
    status VARCHAR(20) COMMENT '状态：running/success/failed',
    items_crawled INT COMMENT '爬取总数',
    items_new INT COMMENT '新增数量',
    items_updated INT COMMENT '更新数量',
    error_message TEXT COMMENT '错误信息'
) COMMENT='爬取任务记录';

-- 25. 操作日志
CREATE TABLE IF NOT EXISTS operation_logs (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    user_id INT UNSIGNED NOT NULL COMMENT '操作用户ID',
    operation_type VARCHAR(50) NOT NULL COMMENT '操作类型：INSERT/UPDATE/DELETE等',
    target_type VARCHAR(50) COMMENT '操作目标类型（表名/模块）',
    target_id VARCHAR(100) COMMENT '操作对象ID',
    old_value TEXT COMMENT '变更前数据(JSON)',
    new_value TEXT COMMENT '变更后数据(JSON)',
    ip VARCHAR(45) COMMENT '操作IP',
    user_agent VARCHAR(300) COMMENT '用户代理',
    created_at DATETIME COMMENT '操作时间'
) COMMENT='管理员操作日志';

-- 26. 系统日志
CREATE TABLE IF NOT EXISTS system_logs (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    log_level VARCHAR(10) NOT NULL COMMENT '日志级别：DEBUG/INFO/WARN/ERROR',
    module VARCHAR(100) COMMENT '模块名称',
    message TEXT COMMENT '日志信息',
    detail TEXT COMMENT '详细内容(JSON)',
    created_at DATETIME COMMENT '记录时间'
) COMMENT='系统运行日志';

-- 27. 安全日志
CREATE TABLE IF NOT EXISTS security_logs (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    user_id INT UNSIGNED COMMENT '相关用户ID',
    event_type VARCHAR(50) NOT NULL COMMENT '事件类型：login_failed/permission_change等',
    ip VARCHAR(45) COMMENT 'IP地址',
    detail TEXT COMMENT '详细信息',
    created_at DATETIME COMMENT '发生时间'
) COMMENT='安全日志';

-- 28. 系统配置
CREATE TABLE IF NOT EXISTS system_configs (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    config_key VARCHAR(100) NOT NULL UNIQUE COMMENT '配置键',
    config_value TEXT NOT NULL COMMENT '配置值',
    description VARCHAR(200) COMMENT '描述',
    updated_at DATETIME COMMENT '更新时间',
    updated_by INT UNSIGNED COMMENT '更新人ID',
    INDEX idx_config_key (config_key)
) COMMENT='系统配置表';

-- 29. 消息通知
CREATE TABLE IF NOT EXISTS notifications (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    user_id INT UNSIGNED NOT NULL COMMENT '接收用户ID',
    type VARCHAR(50) NOT NULL COMMENT '通知类型：audit_result/new_follower等',
    title VARCHAR(200) COMMENT '通知标题',
    content TEXT COMMENT '通知内容',
    is_read BOOLEAN DEFAULT FALSE COMMENT '是否已读',
    extra_data TEXT COMMENT '附加数据(JSON)',
    created_at DATETIME COMMENT '创建时间'
) COMMENT='消息通知';

-- 30. 审核记录表
CREATE TABLE IF NOT EXISTS audit_records (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    content_id VARCHAR(100) COMMENT '内容ID',
    content_type VARCHAR(50) NOT NULL COMMENT '内容类型：comment/post/upload等',
    source_type VARCHAR(50) COMMENT '来源表名',
    content TEXT NOT NULL COMMENT '待审核内容',
    submitter_id INT UNSIGNED NOT NULL COMMENT '提交者用户ID',
    auto_audit_result VARCHAR(20) DEFAULT 'pending' COMMENT '自动审核结果',
    manual_audit_result VARCHAR(20) DEFAULT 'pending' COMMENT '人工审核结果',
    auditor_id INT UNSIGNED COMMENT '审核人ID',
    audit_time DATETIME COMMENT '审核时间',
    reject_reason VARCHAR(500) COMMENT '拒绝原因',
    created_at DATETIME NOT NULL COMMENT '创建时间',
    INDEX idx_content_type (content_type),
    INDEX idx_submitter (submitter_id)
) COMMENT='审核记录表';

-- 31. 处罚记录表
CREATE TABLE IF NOT EXISTS penalty_records (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    user_id INT UNSIGNED NOT NULL COMMENT '被处罚用户ID',
    penalty_type VARCHAR(50) NOT NULL COMMENT '处罚类型',
    reason TEXT NOT NULL COMMENT '处罚原因',
    operator_id INT UNSIGNED NOT NULL COMMENT '操作人ID',
    penalty_time DATETIME NOT NULL COMMENT '处罚时间',
    expire_time DATETIME COMMENT '过期时间',
    status TINYINT DEFAULT 1 COMMENT '状态：1-生效 0-已解除',
    remark TEXT COMMENT '备注',
    created_at DATETIME NOT NULL COMMENT '创建时间'
) COMMENT='处罚记录表';

-- 32. 申诉记录表
CREATE TABLE IF NOT EXISTS appeal_records (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    penalty_id BIGINT UNSIGNED NOT NULL COMMENT '处罚记录ID',
    user_id INT UNSIGNED NOT NULL COMMENT '申诉用户ID',
    appeal_reason TEXT NOT NULL COMMENT '申诉理由',
    evidence TEXT COMMENT '证据',
    status VARCHAR(20) DEFAULT 'pending' COMMENT '状态',
    review_result VARCHAR(20) COMMENT '复审结果',
    reviewer_id INT UNSIGNED COMMENT '复审人ID',
    review_time DATETIME COMMENT '复审时间',
    review_remark TEXT COMMENT '复审备注',
    created_at DATETIME NOT NULL COMMENT '创建时间'
) COMMENT='申诉记录表';

-- 33. 公告表
CREATE TABLE IF NOT EXISTS announcements (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    title VARCHAR(200) NOT NULL COMMENT '公告标题',
    content TEXT NOT NULL COMMENT '公告内容',
    position VARCHAR(50) DEFAULT 'global' COMMENT '展示位置',
    target_audience VARCHAR(50) DEFAULT 'all' COMMENT '目标受众',
    start_time DATETIME COMMENT '开始时间',
    end_time DATETIME COMMENT '结束时间',
    status TINYINT DEFAULT 1 COMMENT '状态：1-发布 0-下线',
    created_by INT UNSIGNED COMMENT '创建人ID',
    view_count INT DEFAULT 0 COMMENT '查看次数',
    created_at DATETIME NOT NULL COMMENT '创建时间',
    updated_at DATETIME COMMENT '更新时间'
) COMMENT='公告表';

-- 34. 用户行为记录表
CREATE TABLE IF NOT EXISTS user_behaviors (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    user_id INT UNSIGNED NOT NULL COMMENT '用户ID',
    behavior_type VARCHAR(50) NOT NULL COMMENT '行为类型',
    target_type VARCHAR(50) COMMENT '目标类型',
    target_id VARCHAR(100) COMMENT '目标对象ID',
    target_desc VARCHAR(500) COMMENT '目标描述',
    ip VARCHAR(45) COMMENT 'IP地址',
    device VARCHAR(200) COMMENT '设备信息',
    detail TEXT COMMENT '行为详情(JSON)',
    created_at DATETIME NOT NULL COMMENT '操作时间'
) COMMENT='用户行为记录表';

-- 35. 违规类型配置表
CREATE TABLE IF NOT EXISTS violation_types (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    type_code VARCHAR(50) NOT NULL UNIQUE COMMENT '违规类型编码',
    type_name VARCHAR(100) NOT NULL COMMENT '违规类型名称',
    severity_level TINYINT NOT NULL COMMENT '严重等级：1-轻微 2-一般 3-严重 4-特别严重',
    default_penalty VARCHAR(50) COMMENT '默认处罚',
    description TEXT COMMENT '描述说明',
    status TINYINT DEFAULT 1 COMMENT '状态：1-启用 0-禁用',
    created_at DATETIME NOT NULL COMMENT '创建时间',
    updated_at DATETIME COMMENT '更新时间'
) COMMENT='违规类型配置表';

-- 插入默认违规类型数据
INSERT IGNORE INTO violation_types (type_code, type_name, severity_level, default_penalty, description, status, created_at) VALUES
('spam_comment', '垃圾评论', 1, 'warning', '发布无关内容、广告等', 1, NOW()),
('inappropriate_content', '不当内容', 2, 'temp_ban', '发布色情、暴力、侮辱性内容', 1, NOW()),
('fake_identity', '虚假身份', 2, 'temp_ban', '使用虚假身份或冒用他人身份', 1, NOW()),
('copyright_violation', '版权侵权', 3, 'permanent_ban', '上传未经授权的内容', 1, NOW()),
('malicious_attack', '恶意攻击', 4, 'permanent_ban', '恶意攻击系统或其他用户', 1, NOW()),
('frequent_operation', '频繁操作', 1, 'warning', '短时间内频繁操作，疑似机器行为', 1, NOW()),
('illegal_upload', '违规上传', 2, 'temp_ban', '上传不符合规范的文件', 1, NOW());
