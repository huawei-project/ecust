from easydict import EasyDict

configer = EasyDict()

configer.datapath = "/datasets/ECUST2019"
configer.logspath = "/home/louishsu/Work/Workspace/HUAWEI/pytorch/logs"
configer.mdlspath = "/home/louishsu/Work/Workspace/HUAWEI/pytorch/modelfiles"

configer.splitmode  = 'split_2'

configer.facesize   = (64, 64)
configer.n_channels = 1
configer.n_classes  = 40

# configer.modelname = "analysis_vgg11_channels"
# configer.modelname = "{}_{}".format(configer.modelname, configer.splitmode)
# configer.modelname = "analysis_vgg11_channels_split1"
configer.modelname = "analysis_vgg11_channels_split2"

configer.lossname  = "crossent"
configer.learningrate = 0.001
configer.batchsize = 256
configer.n_epoch   = 300
configer.earlystopping = True

configer.stepsize = 120
configer.gamma = 0.2
