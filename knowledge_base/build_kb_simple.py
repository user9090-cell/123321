#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化版知识库构建脚本
用于演示和测试
"""

import os
import json
import hashlib
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

def create_sample_knowledge_base():
    """创建示例知识库数据"""
    
    # 创建知识库目录
    chroma_db_dir = PROJECT_ROOT / "backend" / "chroma_db"
    chroma_db_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建示例数据
    sample_data = [
        {
            "id": "1",
            "title": "会理古城",
            "content": "会理古城位于四川省凉山彝族自治州会理市，始建于明洪武十五年（1382年），距今已有600多年历史。古城保存完好，是四川保存最完整的古城之一。",
            "metadata": {
                "开放时间": "全天开放",
                "门票价格": "免费",
                "建议游览时间": "2-3小时",
                "最佳游览季节": "春秋季",
                "tags": ["古城", "历史文化", "免费景点"],
                "keywords": ["会理古城", "明清建筑", "钟鼓楼"],
                "location": "会理市区",
                "lat": 26.6584,
                "lng": 102.2437,
                "rating": 4.8
            }
        },
        {
            "id": "2",
            "title": "会理会议纪念地",
            "content": "会理会议纪念地位于四川省会理市城郊乡铁厂村，是红军长征途中召开重要会议的地点。1935年5月12日，中共中央政治局在这里召开了著名的'会理会议'。",
            "metadata": {
                "开放时间": "8:30-17:30（周一闭馆）",
                "门票价格": "免费（需身份证登记）",
                "建议游览时间": "1-2小时",
                "最佳游览季节": "全年",
                "tags": ["红色旅游", "爱国主义教育", "历史遗迹"],
                "keywords": ["会理会议", "红军长征", "革命历史"],
                "location": "城郊乡铁厂村",
                "lat": 26.6452,
                "lng": 102.2518,
                "rating": 4.9
            }
        },
        {
            "id": "3",
            "title": "会理绿陶",
            "content": "会理绿陶是会理市的传统手工艺品，起源于明代，已有600多年历史。因其釉色青翠如玉而得名，是四川省非物质文化遗产。",
            "metadata": {
                "开放时间": "9:00-18:00",
                "门票价格": "体验价80-200元",
                "建议游览时间": "2-4小时",
                "最佳游览季节": "全年适宜",
                "tags": ["手工艺品", "非物质文化遗产", "文化体验"],
                "keywords": ["绿陶", "传统工艺", "手工制作"],
                "location": "会理市区",
                "lat": 26.6601,
                "lng": 102.2403,
                "rating": 4.7
            }
        },
        {
            "id": "4",
            "title": "龙肘山",
            "content": "龙肘山位于会理市西北部，海拔3585米，是会理市的最高峰。因山势蜿蜒如龙，山顶似肘而得名，是观赏云海、日出的绝佳地点。",
            "metadata": {
                "开放时间": "全天开放（建议白天游览）",
                "门票价格": "免费",
                "建议游览时间": "1天",
                "最佳游览季节": "5-10月",
                "tags": ["自然风光", "登山", "云海日出"],
                "keywords": ["龙肘山", "最高峰", "云海", "日出"],
                "location": "会理市西北部",
                "lat": 26.7123,
                "lng": 102.1856,
                "rating": 4.8
            }
        },
        {
            "id": "5",
            "title": "会理美食",
            "content": "会理地处川滇交界，饮食文化融合了四川和云南的特色，形成了独特的地方风味。特色美食包括羊肉粉、鸡火丝饵块、铜火锅、金沙江鱼等。",
            "metadata": {
                "开放时间": "各餐厅营业时间不同",
                "门票价格": "无",
                "建议游览时间": "用餐时间",
                "最佳游览季节": "全年",
                "tags": ["美食", "地方特色", "餐饮"],
                "keywords": ["羊肉粉", "鸡火丝饵块", "铜火锅", "金沙江鱼"],
                "location": "会理市区各餐厅",
                "lat": 26.6589,
                "lng": 102.2421,
                "rating": 4.6
            }
        }
    ]
    
    # 保存为JSON文件（模拟向量数据库）
    knowledge_base_file = chroma_db_dir / "knowledge_base.json"
    with open(knowledge_base_file, 'w', encoding='utf-8') as f:
        json.dump(sample_data, f, ensure_ascii=False, indent=2)
    
    print(f"示例知识库已创建，包含 {len(sample_data)} 个条目")
    print(f"保存位置: {knowledge_base_file}")
    
    # 创建处理后的数据
    processed_dir = SCRIPT_DIR / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    
    processed_file = processed_dir / "processed_data.json"
    with open(processed_file, 'w', encoding='utf-8') as f:
        json.dump(sample_data, f, ensure_ascii=False, indent=2)
    
    print(f"处理后数据: {processed_file}")
    
    return sample_data

def print_knowledge_base_stats(data):
    """打印知识库统计信息"""
    print("\n知识库统计信息:")
    print("=" * 40)
    print(f"总条目数: {len(data)}")
    
    # 统计标签
    all_tags = []
    for item in data:
        if 'tags' in item['metadata']:
            all_tags.extend(item['metadata']['tags'])
    
    unique_tags = set(all_tags)
    print(f"唯一标签数: {len(unique_tags)}")
    print(f"标签列表: {', '.join(sorted(unique_tags))}")
    
    # 显示每个条目
    print("\n知识库条目:")
    for i, item in enumerate(data, 1):
        print(f"{i}. {item['title']}")
        print(f"   位置: {item['metadata'].get('location', '未知')}")
        print(f"   开放时间: {item['metadata'].get('开放时间', '未知')}")
        print(f"   门票: {item['metadata'].get('门票价格', '未知')}")
        print()

if __name__ == "__main__":
    print("开始构建会理市AI数字人导游知识库...")
    print("=" * 50)
    
    # 创建知识库
    knowledge_data = create_sample_knowledge_base()
    
    # 打印统计信息
    print_knowledge_base_stats(knowledge_data)
    
    print("知识库构建完成！")
    print("=" * 50)
    print("\n下一步:")
    print("1. 安装完整依赖: pip install -r backend/requirements.txt")
    print("2. 运行完整构建脚本: python knowledge_base/build_kb.py")
    print("3. 启动后端服务: python backend/app.py")
