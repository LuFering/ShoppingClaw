"""
Streamlit Web Application
购物助手 Web 界面
"""
import streamlit as st


def main():
    st.set_page_config(
        page_title="ShoppingClaw - 智能购物助手",
        page_icon="🛒",
        layout="wide"
    )
    
    st.title("🛒 ShoppingClaw")
    st.subheader("智能购物助手")
    
    # TODO: 实现主要功能界面
    st.write("请输入您要搜索的商品...")


if __name__ == "__main__":
    main()
