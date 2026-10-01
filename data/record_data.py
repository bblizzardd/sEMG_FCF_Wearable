#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
record_data.py - Wrapper trỏ tới record_emg_csv.py để tương thích cấu trúc thư mục data/
"""
import os
import sys

# Chuyển hướng chạy record_emg_csv.py ở thư mục gốc
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, root_dir)

import record_emg_csv

if __name__ == "__main__":
    record_emg_csv.main()
