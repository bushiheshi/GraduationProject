def main():
    print("请选择一个操作：")
    print("1. 加法")
    print("2. 减法")
    print("3. 乘法")
    print("4. 除法")

    choice = input("请输入你的选择（1/2/3/4）：")

    if choice == '1':
        num1 = float(input("请输入第一个数字："))
        num2 = float(input("请输入第二个数字："))
        result = num1 + num2
        print(f"结果是：{result}")
    elif choice == '2':
        num1 = float(input("请输入第一个数字："))
        num2 = float(input("请输入第二个数字："))
        result = num1 - num2
        print(f"结果是：{result}")
    elif choice == '3':
        num1 = float(input("请输入第一个数字："))
        num2 = float(input("请输入第二个数字："))
        result = num1 * num2
        print(f"结果是：{result}")
    elif choice == '4':
        num1 = float(input("请输入第一个数字："))
        num2 = float(input("请输入第二个数字："))
        if num2 != 0:
            result = num1 / num2
            print(f"结果是：{result}")
        else:
            print("错误：除数不能为零")
    else:
        print("无效的选择，请重新运行程序并输入有效的选项。")


if __name__ == "__main__":
    main()
