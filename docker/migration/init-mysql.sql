-- MySQL 初始化脚本：创建 6 张表（与服务器 seitem 库结构一致）
-- 由 docker-compose 启动时自动执行

CREATE DATABASE IF NOT EXISTS seitem
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE seitem;

-- ============================================
-- 1. museums 博物馆信息
-- ============================================
CREATE TABLE IF NOT EXISTS museums
(
    id             INT UNSIGNED AUTO_INCREMENT COMMENT '主键ID'
        PRIMARY KEY,
    name           VARCHAR(200)   NOT NULL COMMENT '博物馆官方完整名称',
    short_name     VARCHAR(100)   NULL COMMENT '简称',
    country        VARCHAR(100)   NOT NULL COMMENT '国家',
    city           VARCHAR(100)   NULL COMMENT '城市',
    website        VARCHAR(255)   NULL COMMENT '官网URL',
    collection_url VARCHAR(255)   NULL COMMENT '藏品搜索URL',
    created_at     DATETIME       NULL,
    updated_at     DATETIME       NULL,
    latitude       DECIMAL(10, 7) NULL COMMENT '博物馆纬度',
    longitude      DECIMAL(10, 7) NULL COMMENT '博物馆经度'
) COMMENT '博物馆信息';

-- ============================================
-- 2. dynasties 历史朝代
-- ============================================
CREATE TABLE IF NOT EXISTS dynasties
(
    id          INT UNSIGNED AUTO_INCREMENT COMMENT '主键ID'
        PRIMARY KEY,
    name_zh     VARCHAR(50)  NOT NULL COMMENT '中文朝代名称',
    name_en     VARCHAR(100) NULL COMMENT '英文名称',
    start_year  INT          NULL COMMENT '起始年份（公元前为负）',
    end_year    INT          NULL COMMENT '结束年份',
    description TEXT         NULL COMMENT '朝代简介',
    created_at  TIMESTAMP    NULL COMMENT '创建时间'
) COMMENT '历史朝代';

-- ============================================
-- 3. artists 艺术家表
-- ============================================
CREATE TABLE IF NOT EXISTS artists
(
    id         INT UNSIGNED AUTO_INCREMENT COMMENT '主键ID'
        PRIMARY KEY,
    name_zh    VARCHAR(100) NULL COMMENT '中文名',
    name_en    VARCHAR(200) NULL COMMENT '英文名',
    birth_year INT          NULL COMMENT '生年',
    death_year INT          NULL COMMENT '卒年',
    dynasty_id INT UNSIGNED NULL COMMENT '主要活跃朝代ID',
    biography  TEXT         NULL COMMENT '生平介绍',
    baidu_url  VARCHAR(255) NULL COMMENT '百度百科链接',
    wiki_url   VARCHAR(255) NULL COMMENT '维基百科链接',
    created_at TIMESTAMP    NULL COMMENT '创建时间',
    updated_at TIMESTAMP    NULL COMMENT '更新时间'
) COMMENT '艺术家（书画家等）';

-- ============================================
-- 4. artifacts 文物主表
-- ============================================
CREATE TABLE IF NOT EXISTS artifacts
(
    id               INT UNSIGNED AUTO_INCREMENT COMMENT '主键ID'
        PRIMARY KEY,
    object_id        VARCHAR(100) NOT NULL COMMENT '博物馆原始ID或系统生成唯一标识',
    title_zh         VARCHAR(500) NULL COMMENT '中文名称',
    title_en         VARCHAR(500) NOT NULL COMMENT '英文原始名称',
    time_period      VARCHAR(200) NULL COMMENT '年代描述（原始）',
    dynasty_id       INT UNSIGNED NULL COMMENT '所属朝代ID',
    type             VARCHAR(100) NULL COMMENT '文物类型（如 Painting, Ceramics）',
    material         VARCHAR(200) NULL COMMENT '材质',
    description      TEXT         NULL COMMENT '文物介绍文本',
    dimensions       VARCHAR(200) NULL COMMENT '尺寸',
    museum_id        INT UNSIGNED NOT NULL COMMENT '现藏博物馆ID',
    location_id      INT UNSIGNED NULL COMMENT '博物馆所在地ID',
    detail_url       VARCHAR(500) NULL COMMENT '博物馆详情页URL',
    image_url        VARCHAR(500) NULL COMMENT '主图原图URL',
    image_path       VARCHAR(500) NULL COMMENT '本地存储相对路径',
    credit_line      VARCHAR(300) NULL COMMENT '版权/来源说明',
    accession_number VARCHAR(100) NULL COMMENT '馆藏编号',
    crawl_date       DATE         NULL COMMENT '爬取日期',
    image_validated  TINYINT      NULL COMMENT '图片有效性验证 0/1',
    last_updated     TIMESTAMP    NULL COMMENT '最后更新时间',
    created_at       TIMESTAMP    NULL COMMENT '创建时间',
    provenance       TEXT         NULL COMMENT '文物流转或来源脉络',
    current_status   VARCHAR(100) NULL COMMENT '当前展出、保存或数字开放状态',

    INDEX idx_museum_object (museum_id, object_id)
) COMMENT '文物主表';

-- ============================================
-- 5. artifact_images 文物多图片表
-- ============================================
CREATE TABLE IF NOT EXISTS artifact_images
(
    id          INT UNSIGNED AUTO_INCREMENT COMMENT '主键ID'
        PRIMARY KEY,
    artifact_id INT UNSIGNED NOT NULL COMMENT '文物ID',
    image_url   VARCHAR(500) NOT NULL COMMENT '图片URL',
    image_path  VARCHAR(500) NULL COMMENT '本地存储路径',
    is_primary  TINYINT      NULL COMMENT '是否主图 0/1',
    sort_order  INT          NULL COMMENT '排序序号'
) COMMENT '文物多图片';

-- ============================================
-- 6. artifact_artist 文物与艺术家关联表
-- ============================================
CREATE TABLE IF NOT EXISTS artifact_artist
(
    artifact_id       INT UNSIGNED NOT NULL COMMENT '文物ID',
    artist_id         INT UNSIGNED NOT NULL COMMENT '艺术家ID',
    relationship_type VARCHAR(50)  NULL COMMENT '关系类型（creator/collector等）',

    INDEX idx_artifact_artist (artifact_id, artist_id)
) COMMENT '文物与艺术家关联';
