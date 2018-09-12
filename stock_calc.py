def stock_calc( maesu_count, chumae_percent ):
    print("#############################################")
    print("stock_cal maesu_count {} chumae_percent {}".format( maesu_count, chumae_percent ))
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
        stock_value = round(init_stock_value * ((1 + chumae_percent/100) ** cnt) , 2)
        stock_count = int(base_money / stock_value)

        result_price_list.append(stock_value)
        result_maesu_list.append(stock_count)
        total_value_list.append(round(stock_count * stock_value,2) )
        # print( str(sum(total_value_list)) + ' '  +  str(sum(result_maesu_list) ) )
        sum_list.append(round( sum(total_value_list) / sum(result_maesu_list), 2)  )
    
    print("current_price: ", sep='')
    print(result_price_list) 
    print("-" * 100)
    print("stock amount per maesu:", sep= '' )
    print(result_maesu_list) 
    print("-" * 100)
    # print(total_value_list)
    print("maeip-danga: ", sep='')
    print(sum_list)
    print("-" * 100)
    print("percent from maeip-danga: ", sep='')
    print( [round((x/y* 100) -100, 2 )for x, y in zip(result_price_list , sum_list)]  )
    print("-" * 100)

if __name__ == '__main__':
    stock_calc( 4, 1 ) # 4번만 추가 매수 하고 싶고 2% 오를 때 마다 매수 하는 경우 