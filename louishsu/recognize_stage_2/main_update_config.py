'''
@Description: 
@Version: 1.0.0
@Auther: louishsu
@E-mail: is.louishsu@foxmail.com
@Date: 2019-08-10 10:30:40
@LastEditTime: 2019-09-17 13:56:58
@Update: 
'''
import os
import time
import numpy as np
from matplotlib import pyplot as plt 
from easydict import EasyDict

import torch
import torch.nn as nn
import torch.optim as optim
import torch.optim.lr_scheduler as lr_scheduler
from torch.cuda import is_available, empty_cache
from torch.autograd import Variable
from torch.utils.data import Dataset, DataLoader
from tensorboardX import SummaryWriter

from datasets import RecognizeDataset
from models import modeldict
from utils import accuracy, gen_markdown_table_2d, parse_log, ImageAttributes

from train import train
from test  import test

def get_configer(n_epoch=150, stepsize=120, batchsize=2**5, lrbase=5e-4, gamma=0.2, cuda=True, 
                dsize=(112//2, 96//2), n_channel=25, n_class=80, 
                datatype='Multi', usedChannels=[i+1 for i in range(25)], 
                splitratio=[0.6, 0.2, 0.2], splitcount=1, 
                modelbase= 'recognize_resnet34', 
                datapath = '/datasets/Indoordetect', savepath = 'checkpoints', 
                hist=False, training_no_glass=False, training_no_sunglass=True):    # TODO: condition
    """
    Params:
        n_epoch:        {int}                   总计迭代周期数
        stepsize:       {int}                   学习率衰减周期
        batchsize:      {int}                   批次大小
        lrbase:         {float}                 初始学习率
        gamma:          {float}                 学习率衰减倍率
        cuda:           {bool}                  是否使用cuda加速
        dsize:          {tuple(int, int)}       数据空间尺寸
        n_channel:      {int}                   数据通道数
        n_class:        {int}                   数据类别数
        datatype:       {str}                   多光谱或可见光
        usedChannels:   {list[int] or str}      使用的通道索引
        splitratio:     {list[float(3)]}        划分比例
        splitcount:     {int}                   当前划分比例下，当前次随机划分
        modelbase:      {str}                   使用模型
        datapath:       {str}                   数据根目录
        savepath:       {str}                   程序输出目录
    """
    configer = EasyDict()

    ## -------------------------------------------------------------
    configer.hist = hist
    configer.training_no_glass = training_no_glass          # no sunglasses and glasses
    configer.training_no_sunglass = training_no_sunglass    # no sunglasses

    ## -------------------------- 训练相关 --------------------------
    configer.n_epoch  = n_epoch
    configer.stepsize = stepsize
    configer.batchsize = batchsize
    configer.lrbase = lrbase
    configer.gamma = gamma
    configer.cuda = cuda
    configer.savepath = savepath

    ## ------------------------- 数据集相关 -------------------------
    configer.datapath = datapath
    configer.dsize = dsize
    configer.n_channel = n_channel          # 一份多光谱数据，包含25通道
    configer.n_class = n_class              # 人员数目共92人

    configer.datatype = datatype            # "Multi", "RGB"
    configer.usedChannels = usedChannels    # 多光谱: 列表，包含所用通道索引(1~25)； 可见光: 字符串，"RGB"或"R", "G", "B"
    configer.splitratio = splitratio        # 划分比例
    configer.splitcount = splitcount

    ## -------------------------- 模型相关 --------------------------
    configer.modelbase = modelbase

    ## ========================== 无需修改 ==========================
    configer.splitmode = 'split_112x96_[{:.2f}:{:.2f}:{:.2f}]_[{:d}]'.\
                format(
                configer.splitratio[0], configer.splitratio[1], configer.splitratio[2], 
                configer.splitcount)
    configer.n_usedChannels = len(configer.usedChannels)
    configer.modelname = '[{}]_{}_[{}]'.\
                    format(configer.modelbase, configer.splitmode, 
                            '_'.join(list(map(str, configer.usedChannels))) \
                                if isinstance(configer.usedChannels, list) \
                                else configer.usedChannels)

    configer.logspath = '{}/{}/logs'.format(configer.savepath, configer.modelname)
    configer.mdlspath = '{}/{}/models'.format(configer.savepath, configer.modelname)

    return configer

def main_3_1(make_table_figure=False):

    datatypes   = ["Multi", "RGB"]
    splitcounts = [i for i in range(1, 11)]
    trains      = [0.1*(i + 1) for i in range(7)]
    H, W = len(splitcounts), len(trains)

    if make_table_figure:

        for datatype in datatypes:

            print("Generating tables and figures [{}]...".format(datatype))

            table_data = np.loadtxt("images/3_1_<data>_[{}].txt".format(datatype))
            table_data_acc, table_data_loss = np.vsplit(table_data, 2)      # 按竖直方向划分为两块，即上下

            ## 做表格
            head_name = "count/比例"
            rows_name = [str(i) for i in splitcounts] + ['average']
            cols_name = ["{:.2f}: {:.2f}: 0.2".format(i, 0.8 - i) for i in trains]
            
            table_acc  = gen_markdown_table_2d(head_name, rows_name, cols_name, table_data_acc)
            table_loss = gen_markdown_table_2d(head_name, rows_name, cols_name, table_data_loss)
        
            with open("images/3_1_<table>_[{}].md".format(datatype), 'w') as f:
                f.write("\n\nacc\n")
                f.write(table_acc)
                f.write("\n\nloss\n")
                f.write(table_loss)
            
            ## 作图
            plt.figure()
            
            plt.subplot(121); plt.title("acc")
            avg_acc = table_data_acc[-1]
            plt.bar(np.arange(avg_acc.shape[0]),  avg_acc )
            
            plt.subplot(122); plt.title("loss")
            avg_loss = table_data_loss[-1]
            plt.bar(np.arange(avg_loss.shape[0]), avg_loss)
            
            plt.savefig("images/3_1_<figure>_[{}].png".format(datatype))

        return

    start_time = time.time(); elapsed_time = 0

    for datatype in datatypes:

        data_acc  = np.zeros(shape=(H, W))
        data_loss = np.zeros(shape=(H, W))

        for i in range(H):                  # 1, 2, ..., 5

            splitcount = splitcounts[i]
            TEST = 0.2

            for j in range(W):

                valid = 1 - TEST - trains[j]
                splitratio = [trains[j], valid, TEST]

                configer = get_configer(datatype=datatype, splitratio=splitratio, splitcount=splitcount, 
                    usedChannels=[i+1 for i in range(25)] if datatype=="Multi" else "RGB")

                elapsed_time += time.time() - start_time
                start_time    = time.time()
                print("Main 3.1 [{}] [{}]... Elaped >>> {} min".\
                            format(configer.datatype, configer.splitmode, elapsed_time/60))

                logpath = os.path.join(configer.logspath, configer.modelname)
                print(logpath)
                if os.path.exists(logpath):
                    with open(os.path.join(logpath, 'test_log.txt'), 'r') as f:
                        test_log = f.readlines()[0]
                        data_acc[i, j], data_loss[i, j] = parse_log(test_log)
                        print(test_log)
                else:
                    train(configer)
                    data_acc[i, j], data_loss[i, j] = test(configer)
                print("-------------------------------------------------")
        
        ## 保存数据
        avg_acc  = np.mean(data_acc,  axis=0)
        avg_loss = np.mean(data_loss, axis=0)

        table_data_acc  = np.r_[data_acc,  avg_acc.reshape(1, -1) ]
        table_data_loss = np.r_[data_loss, avg_loss.reshape(1, -1)]
        table_data      = np.r_[table_data_acc, table_data_loss]

        np.savetxt("images/3_1_<data>_[{}].txt".format(datatype), table_data)

def main_3_2(make_table_figure=False):

    datatypes   = ["Multi", "RGB"]
    splitcounts = [i for i in range(1, 11)]
    H = len(splitcounts)

    if make_table_figure:

        for datatype in datatypes:

            usedChannels_list = [[i] for i in range(1, 26)] \
                        if datatype == "Multi" else ["R", "G", "B"]
            W = len(usedChannels_list)

            print("Generating tables and figures [{}]...".format(datatype))

            table_data = np.loadtxt("images/3_2_<data>_[{}].txt".format(datatype))
            table_data_acc, table_data_loss = np.vsplit(table_data, 2)      # 按竖直方向划分为两块，即上下

            ## 做表格
            head_name = "count/波段索引"
            rows_name = [str(i) for i in splitcounts] + ['average']
            cols_name = [str(i[0]) for i in usedChannels_list]
            
            table_acc  = gen_markdown_table_2d(head_name, rows_name, cols_name, table_data_acc)
            table_loss = gen_markdown_table_2d(head_name, rows_name, cols_name, table_data_loss)
        
            with open("images/3_2_<table>_[{}].md".format(datatype), 'w') as f:
                f.write("\n\nacc\n")
                f.write(table_acc)
                f.write("\n\nloss\n")
                f.write(table_loss)
            
            ## 作图
            plt.figure()
            
            plt.subplot(121); plt.title("acc")
            avg_acc = table_data_acc[-1]
            plt.bar(np.arange(avg_acc.shape[0]),  avg_acc )
            
            plt.subplot(122); plt.title("loss")
            avg_loss = table_data_loss[-1]
            plt.bar(np.arange(avg_loss.shape[0]), avg_loss)

            plt.savefig("images/3_2_<figure>_[{}].png".format(datatype))

            ## 输出最优波段排序，依据准确率
            avg_acc = table_data_acc[-1]
            order = np.argsort(avg_acc)[::-1] + 1
            print("Best: ", order)

        return

    start_time = time.time(); elapsed_time = 0

    for datatype in datatypes:
        
        usedChannels_list = [[i] for i in range(1, 26)] \
                    if datatype == "Multi" else ["R", "G", "B"]
        W = len(usedChannels_list)

        data_acc  = np.zeros(shape=(H, W))
        data_loss = np.zeros(shape=(H, W))
        
        for i in range(len(splitcounts)):
            splitcount = splitcounts[i]

            for j in range(len(usedChannels_list)):
                usedChannels = usedChannels_list[j]

                configer = get_configer(datatype=datatype, 
                            splitcount=splitcount, usedChannels=usedChannels)

                elapsed_time += time.time() - start_time
                start_time    = time.time()
                print("Main 3.2 [{}] [{}] {}... Elaped >>> {} min".\
                            format(configer.datatype, configer.splitmode, usedChannels, elapsed_time/60))

                logpath = os.path.join(configer.logspath, configer.modelname)
                print(logpath)
                if os.path.exists(logpath):
                    with open(os.path.join(logpath, 'test_log.txt'), 'r') as f:
                        test_log = f.readlines()[0]
                        data_acc[i, j], data_loss[i, j] = parse_log(test_log)
                        print(test_log)
                else:
                    train(configer)
                    data_acc[i, j], data_loss[i, j] = test(configer)
                print("-------------------------------------------------")
        
        ## 保存数据
        avg_acc  = np.mean(data_acc,  axis=0)
        avg_loss = np.mean(data_loss, axis=0)

        table_data_acc  = np.r_[data_acc,  avg_acc.reshape(1, -1) ]
        table_data_loss = np.r_[data_loss, avg_loss.reshape(1, -1)]
        table_data      = np.r_[table_data_acc, table_data_loss]

        np.savetxt("images/3_2_<data>_[{}].txt".format(datatype), table_data)

def main_3_3(make_table_figure=False):

    ORDER = [
        23, 19, 24, 16,  7,
         8, 21, 13, 17,  3,
         1, 14, 22, 11,  9, 
        20, 15, 12,  5,  6,
         4, 25, 18,  2, 10
        ]
    usedChannels_list = [ORDER[: i+1] for i in range(len(ORDER))]
    splitcounts = [i for i in range(1, 11)]
    H, W = len(splitcounts), len(usedChannels_list)

    if make_table_figure:

        print("Generating tables and figures [Multi]...")

        table_data = np.loadtxt("images/3_3_<data>_[Multi].txt")
        table_data_acc, table_data_loss = np.vsplit(table_data, 2)      # 按竖直方向划分为两块，即上下

        ## 做表格
        head_name = "count/组合数"
        rows_name = [str(i) for i in splitcounts] + ['average']
        cols_name = [str(i+1) for i in range(W)]
        
        table_acc  = gen_markdown_table_2d(head_name, rows_name, cols_name, table_data_acc)
        table_loss = gen_markdown_table_2d(head_name, rows_name, cols_name, table_data_loss)
    
        with open("images/3_3_<table>_[Multi].md", 'w') as f:
            f.write("\n\nacc\n")
            f.write(table_acc)
            f.write("\n\nloss\n")
            f.write(table_loss)
        
        ## 作图
        plt.figure()
        
        plt.subplot(121); plt.title("acc")
        avg_acc = table_data_acc[-1]
        plt.bar(np.arange(avg_acc.shape[0]),  avg_acc )
        
        plt.subplot(122); plt.title("loss")
        avg_loss = table_data_loss[-1]
        plt.bar(np.arange(avg_loss.shape[0]), avg_loss)

        plt.savefig("images/3_3_<figure>_[Multi].png")

        return

    start_time = time.time(); elapsed_time = 0

    data_acc  = np.zeros(shape=(H, W))
    data_loss = np.zeros(shape=(H, W))
    
    for i in range(len(splitcounts)):
        splitcount = splitcounts[i]
        
        for j in range(len(usedChannels_list)):
            usedChannels = usedChannels_list[j]
            
            configer = get_configer(splitcount=splitcount, usedChannels=usedChannels)

            elapsed_time += time.time() - start_time
            start_time    = time.time()
            print("Main 3.3 [Multi] [{}] {}... Elaped >>> {} min".\
                        format(configer.splitmode, usedChannels, elapsed_time/60))

            logpath = os.path.join(configer.logspath, configer.modelname)
            print(logpath)
            if os.path.exists(logpath):
                with open(os.path.join(logpath, 'test_log.txt'), 'r') as f:
                    test_log = f.readlines()[0]
                    data_acc[i, j], data_loss[i, j] = parse_log(test_log)
                    print(test_log)
            else:
                train(configer)
                data_acc[i, j], data_loss[i, j] = test(configer)
            print("-------------------------------------------------")
    
    ## 保存数据
    avg_acc  = np.mean(data_acc,  axis=0)
    avg_loss = np.mean(data_loss, axis=0)

    table_data_acc  = np.r_[data_acc,  avg_acc.reshape(1, -1) ]
    table_data_loss = np.r_[data_loss, avg_loss.reshape(1, -1)]
    table_data      = np.r_[table_data_acc, table_data_loss]

    np.savetxt("images/3_3_<data>_[Multi].txt", table_data)

def main_3_4(make_table_figure=False):

    ORDER = [i+1 for i in range(25)]
    usedChannels_list = [ORDER[: : i+1] for i in range(len(ORDER))]
    splitcounts = [i for i in range(1, 11)]
    H, W = len(splitcounts), len(usedChannels_list)

    if make_table_figure:

        print("Generating tables and figures [Multi]...")

        table_data = np.loadtxt("images/3_4_<data>_[Multi].txt")
        table_data_acc, table_data_loss = np.vsplit(table_data, 2)      # 按竖直方向划分为两块，即上下

        ## 做表格
        head_name = "count/波段步长"
        rows_name = [str(i) for i in splitcounts] + ['average']
        cols_name = [str(i+1) for i in range(W)]
        
        table_acc  = gen_markdown_table_2d(head_name, rows_name, cols_name, table_data_acc)
        table_loss = gen_markdown_table_2d(head_name, rows_name, cols_name, table_data_loss)
    
        with open("images/3_4_<table>_[Multi].md", 'w') as f:
            f.write("\n\nacc\n")
            f.write(table_acc)
            f.write("\n\nloss\n")
            f.write(table_loss)
        
        ## 作图
        plt.figure()
        
        plt.subplot(121); plt.title("acc")
        avg_acc = table_data_acc[-1]
        plt.bar(np.arange(avg_acc.shape[0]),  avg_acc )
        
        plt.subplot(122); plt.title("loss")
        avg_loss = table_data_loss[-1]
        plt.bar(np.arange(avg_loss.shape[0]), avg_loss)

        plt.savefig("images/3_4_<figure>_[Multi].png")

        return

    start_time = time.time(); elapsed_time = 0

    data_acc  = np.zeros(shape=(H, W))
    data_loss = np.zeros(shape=(H, W))
    
    for i in range(len(splitcounts)):
        splitcount = splitcounts[i]
        
        for j in range(len(usedChannels_list)):
            usedChannels = usedChannels_list[j]
            
            configer = get_configer(splitcount=splitcount, usedChannels=usedChannels)

            elapsed_time += time.time() - start_time
            start_time    = time.time()
            print("Main 3.4 [Multi] [{}] {}... Elaped >>> {} min".\
                        format(configer.splitmode, usedChannels, elapsed_time/60))

            logpath = os.path.join(configer.logspath, configer.modelname)
            print(logpath)
            if os.path.exists(logpath):
                with open(os.path.join(logpath, 'test_log.txt'), 'r') as f:
                    test_log = f.readlines()[0]
                    data_acc[i, j], data_loss[i, j] = parse_log(test_log)
                    print(test_log)
            else:
                train(configer)
                data_acc[i, j], data_loss[i, j] = test(configer)
            print("-------------------------------------------------")
    
    ## 保存数据
    avg_acc  = np.mean(data_acc,  axis=0)
    avg_loss = np.mean(data_loss, axis=0)

    table_data_acc  = np.r_[data_acc,  avg_acc.reshape(1, -1) ]
    table_data_loss = np.r_[data_loss, avg_loss.reshape(1, -1)]
    table_data      = np.r_[table_data_acc, table_data_loss]

    np.savetxt("images/3_4_<data>_[Multi].txt", table_data)

def main_3_5(make_table_figure=False):

    datatypes   = ["Multi", "RGB"]
    splitcounts = [i for i in range(1, 11)]
    H = len(splitcounts)

    loss = nn.CrossEntropyLoss()

    if make_table_figure:

        illum_types = ["illum1", "illum2", "illum3", "normal"]
        positions   = [i + 1 for i in range(7)]         # 共7个拍摄角度，编号 1 ~ 7
        glass_types = [1, 5, 6]                         # `1`表示无眼镜，`5`表示戴眼镜，`6`表示太阳镜

        for datatype in datatypes:

            print("Generating tables and figures [{}]...".format(datatype))
        
            usedChannels = [i for i in range(1, 26)] \
                        if datatype == "Multi" else "RGB"

            data_acc_illum_types  = np.zeros(shape=(H, len(illum_types)))
            data_loss_illum_types = np.zeros(shape=(H, len(illum_types)))
            data_acc_positions    = np.zeros(shape=(H, len(positions  )))
            data_loss_positions   = np.zeros(shape=(H, len(positions  )))
            data_acc_glass_types  = np.zeros(shape=(H, len(glass_types)))
            data_loss_glass_types = np.zeros(shape=(H, len(glass_types)))
            
            for i in range(len(splitcounts)):
                splitcount = splitcounts[i]

                ## 获取configer
                configer = get_configer(datatype=datatype, 
                            splitcount=splitcount, usedChannels=usedChannels)

                ## 读取保存的测试结果
                logpath = os.path.join(configer.logspath, configer.modelname)
                print(logpath)
                y_pred_prob = np.load(os.path.join(logpath, 'test_out.npy'))

                ## 读取文件列表
                testset = RecognizeDataset(configer.datapath, configer.datatype, 
                        configer.splitmode, 'test', configer.usedChannels)
                y_true = np.array(list(map(lambda x: x[1], testset.samplelist)))
                test_list  = testset.filelist
                test_attr_list = list(map(lambda  x: ImageAttributes(x), test_list))
                del testset

                ## 分析光照
                for j in range(len(illum_types)):
                    illum_type = illum_types[j]

                    # FIXME:
                    # index = list(map(lambda x: x.illum_type==illum_type, test_attr_list))
                    index = list(map(lambda x: x.illum_type==illum_type and \
                                            #    x.glass_type==1 and \
                                               x.position==4, 
                                               test_attr_list))
                    index = np.array(index, dtype=np.bool)

                    y_pred_prob_sub = torch.tensor(y_pred_prob[index])
                    y_true_sub      = torch.tensor(y_true[index])
                    data_acc_illum_types [i, j] = accuracy(y_pred_prob_sub, y_true_sub).cpu().numpy()
                    data_loss_illum_types[i, j] = loss(y_pred_prob_sub, y_true_sub).cpu().numpy()

                ## 分析位置
                for j in range(len(positions)):
                    position = positions[j]

                    # FIXME:
                    # index = list(map(lambda x: x.position==position, test_attr_list))
                    index = list(map(lambda x: x.position==position and \
                                               x.glass_type==1, test_attr_list))
                    index = np.array(index, dtype=np.bool)

                    y_pred_prob_sub = torch.tensor(y_pred_prob[index])
                    y_true_sub      = torch.tensor(y_true[index])
                    data_acc_positions [i, j] = accuracy(y_pred_prob_sub, y_true_sub).cpu().numpy()
                    data_loss_positions[i, j] = loss(y_pred_prob_sub, y_true_sub).cpu().numpy()

                ## 分析眼镜
                for j in range(len(glass_types)):
                    glass_type = glass_types[j]

                    index = list(map(lambda x: x.glass_type==glass_type, test_attr_list))
                    index = np.array(index, dtype=np.bool)

                    y_pred_prob_sub = torch.tensor(y_pred_prob[index])
                    y_true_sub      = torch.tensor(y_true[index])
                    data_acc_glass_types [i, j] = accuracy(y_pred_prob_sub, y_true_sub).cpu().numpy()
                    data_loss_glass_types[i, j] = loss(y_pred_prob_sub, y_true_sub).cpu().numpy()

            ## 绘制表格
            rows_name = [str(i) for i in splitcounts] + ['average']
            
            # =====================================================================================================
            head_name = "count/光照"
            cols_name = illum_types
            # -----------------------------------------------------------------------------------------------------
            data_acc_illum_types  = np.r_[data_acc_illum_types,  np.mean(data_acc_illum_types, axis=0).reshape(1, -1)]
            data_loss_illum_types = np.r_[data_loss_illum_types, np.mean(data_loss_illum_types, axis=0).reshape(1, -1)]
            # -----------------------------------------------------------------------------------------------------
            table_acc_illum_types  = gen_markdown_table_2d(head_name, rows_name, cols_name, data_acc_illum_types )
            table_loss_illum_types = gen_markdown_table_2d(head_name, rows_name, cols_name, data_loss_illum_types)
            with open("images/3_5_<table>_[{}]_[illum_types].txt".format(datatype), 'w') as f:
                f.write("\n\nacc\n")
                f.write(table_acc_illum_types)
                f.write("\n\nloss\n")
                f.write(table_loss_illum_types)
            # -----------------------------------------------------------------------------------------------------
            plt.figure()
            plt.subplot(121); plt.title("acc")
            avg_acc  = data_acc_illum_types[-1]
            plt.bar(np.arange(avg_acc.shape[0]),  avg_acc )
            plt.subplot(122); plt.title("loss")
            avg_loss = data_loss_illum_types[-1]
            plt.bar(np.arange(avg_loss.shape[0]), avg_loss)
            plt.savefig("images/3_5_<figure>_[{}]_[illum_types].png".format(datatype))

            # =====================================================================================================
            head_name = "count/位置"
            cols_name = list(map(str, positions))
            # -----------------------------------------------------------------------------------------------------
            data_acc_positions  = np.r_[data_acc_positions,  np.mean(data_acc_positions, axis=0).reshape(1, -1)]
            data_loss_positions = np.r_[data_loss_positions, np.mean(data_loss_positions, axis=0).reshape(1, -1)]
            # -----------------------------------------------------------------------------------------------------
            table_acc_positions  = gen_markdown_table_2d(head_name, rows_name, cols_name, data_acc_positions )
            table_loss_positions = gen_markdown_table_2d(head_name, rows_name, cols_name, data_loss_positions)
            with open("images/3_5_<table>_[{}]_[positions].md".format(datatype), 'w') as f:
                f.write("\n\nacc\n")
                f.write(table_acc_positions)
                f.write("\n\nloss\n")
                f.write(table_loss_positions)
            # -----------------------------------------------------------------------------------------------------
            plt.figure()
            plt.subplot(121); plt.title("acc")
            avg_acc  = data_acc_positions[-1]
            plt.bar(np.arange(avg_acc.shape[0]),  avg_acc )
            plt.subplot(122); plt.title("loss")
            avg_loss = data_loss_positions[-1]
            plt.bar(np.arange(avg_loss.shape[0]), avg_loss)
            plt.savefig("images/3_5_<figure>_[{}]_[positions].png".format(datatype))

            # =====================================================================================================
            head_name = "count/眼镜"
            cols_name = list(map(str, glass_types))
            # -----------------------------------------------------------------------------------------------------
            data_acc_glass_types  = np.r_[data_acc_glass_types,  np.mean(data_acc_glass_types, axis=0).reshape(1, -1)]
            data_loss_glass_types = np.r_[data_loss_glass_types, np.mean(data_loss_glass_types, axis=0).reshape(1, -1)]
            # -----------------------------------------------------------------------------------------------------
            table_acc_glass_types  = gen_markdown_table_2d(head_name, rows_name, cols_name, data_acc_glass_types )
            table_loss_glass_types = gen_markdown_table_2d(head_name, rows_name, cols_name, data_loss_glass_types)
            with open("images/3_5_<table>_[{}]_[glass_types].txt".format(datatype), 'w') as f:
                f.write("\n\nacc\n")
                f.write(table_acc_glass_types)
                f.write("\n\nloss\n")
                f.write(table_loss_glass_types)
            # -----------------------------------------------------------------------------------------------------
            plt.figure()
            plt.subplot(121); plt.title("acc")
            avg_acc  = data_acc_glass_types[-1]
            plt.bar(np.arange(avg_acc.shape[0]),  avg_acc )
            plt.subplot(122); plt.title("loss")
            avg_loss = data_loss_glass_types[-1]
            plt.bar(np.arange(avg_loss.shape[0]), avg_loss)
            plt.savefig("images/3_5_<figure>_[{}]_[glass_types].png".format(datatype))

        return

    start_time = time.time(); elapsed_time = 0

    for datatype in datatypes:
        
        usedChannels = [i for i in range(1, 26)] \
                    if datatype == "Multi" else "RGB"

        data_acc  = np.zeros(H)
        data_loss = np.zeros(H)
        
        for i in range(len(splitcounts)):
            splitcount = splitcounts[i]

            configer = get_configer(datatype=datatype, 
                        splitcount=splitcount, usedChannels=usedChannels)

            elapsed_time += time.time() - start_time
            start_time    = time.time()
            print("Main 3.2 [{}] [{}] {}... Elaped >>> {} min".\
                        format(configer.datatype, configer.splitmode, usedChannels, elapsed_time/60))

            logpath = os.path.join(configer.logspath, configer.modelname)
            print(logpath)
            if os.path.exists(logpath):
                with open(os.path.join(logpath, 'test_log.txt'), 'r') as f:
                    test_log = f.readlines()[0]
                    data_acc[i], data_loss[i] = parse_log(test_log)
                    print(test_log)
            else:
                train(configer)
                data_acc[i], data_loss[i] = test(configer)
            print("-------------------------------------------------")
        
        ## 保存数据
        avg_acc  = np.mean(data_acc,  axis=0)
        avg_loss = np.mean(data_loss, axis=0)

        table_data_acc  = np.r_[data_acc,  avg_acc ]
        table_data_loss = np.r_[data_loss, avg_loss]
        table_data      = np.r_[table_data_acc.reshape(1, -1), 
                                table_data_loss.reshape(1, -1)]

        np.savetxt("images/3_5_<data>_[{}].txt".format(datatype), table_data)

if __name__ == "__main__":
    
    main_3_1()
    main_3_1(True)

    main_3_2()
    main_3_2(True)

    main_3_3()
    main_3_3(True)

    main_3_4()
    main_3_4(True)

    main_3_5()
    main_3_5(True)
