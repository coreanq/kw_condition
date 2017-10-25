def stock_calc( maesu_count, stop_perc ):
    print("#############################################")
    print("stock_cal maesu_count {} stop_pert {}".format( maesu_count, stop_perc))
    print("#############################################")
    base_money = 10000
    init_stock_value = 100
    result_price_list = []
    result_maesu_list = []
    result_maesu_accu_list = []
    total_value_list = []
    sum_list = []
    stock_value = 0
    for cnt in range(maesu_count):
        stock_value = round(init_stock_value * (stop_perc ** cnt) , 2)
        if( cnt < 2 ):
            stock_count = int(base_money / stock_value)
        else:
            stock_count = int(((2 ** (cnt-1)) * base_money) / stock_value)

        result_price_list.append(stock_value)
        result_maesu_list.append(stock_count)
        total_value_list.append(round(stock_count * stock_value,2) )
        # print( str(sum(total_value_list)) + ' '  +  str(sum(result_maesu_list) ) )
        sum_list.append(round( sum(total_value_list) / sum(result_maesu_list), 2)  )
    
    print("current_price: ", sep='')
    print(result_price_list) 
    print("-" * 100)
    print("stock amount: ", sep= '' )
    print(result_maesu_list) 
    print("-" * 100)
    # print(total_value_list)
    print("danga: ", sep='')
    print(sum_list)
    print("-" * 100)
    print("perc: ", sep='')
    print( [round((x/y* 100) -100, 2 )for x, y in zip(result_price_list , sum_list)]  )
    print("-" * 100)

if __name__ == '__main__':
    stock_calc( 4, 0.85 ) # 3번만 추가 매수 하고 싶고 0.7 떨어질때마다 매수 하는 경우 