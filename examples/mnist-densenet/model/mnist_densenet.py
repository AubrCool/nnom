'''
    Copyright (c) 2018-2019
    Jianjia Ma, Wearable Bio-Robotics Group (WBR)
    majianjia@live.com

    SPDX-License-Identifier: LGPL-3.0

    Change Logs:
    Date           Author       Notes
    2019-02-12     Jianjia Ma   The first version

'''


import matplotlib.pyplot as plt
import os

from keras.models import Sequential, load_model
from keras.models import Model
from keras.datasets import mnist
from keras.datasets import cifar10 #test
from keras.layers import *
from keras.utils import to_categorical
from keras.callbacks import ModelCheckpoint

from nnom_utils import *


model_name = 'mnist_model.h5'
save_dir = model_name #os.path.join(os.getcwd(), model_name)

def dense_block(x, k):

    x1 = Conv2D(k, kernel_size=(3, 3), strides=(1,1), padding="same")(x)
    x1 = fake_clip()(x1)
    x1 = ReLU()(x1)

    x2 = concatenate([x, x1],axis=-1)
    x2 = Conv2D(k, kernel_size=(3, 3), strides=(1,1), padding="same")(x2)
    x2 = fake_clip()(x2)
    x2 = ReLU()(x2)

    x3 = concatenate([x, x1, x2],axis=-1)
    x3 = Conv2D(k, kernel_size=(3, 3), strides=(1,1), padding="same")(x3)
    x3 = fake_clip()(x3)
    x3 = ReLU()(x3)

    x4 = concatenate([x, x1, x2, x3],axis=-1)
    x4 = Conv2D(k, kernel_size=(3, 3), strides=(1,1), padding="same")(x4)
    x4 = fake_clip()(x4)
    x4 = ReLU()(x4)

    return concatenate([x, x1, x2, x3, x4],axis=-1)

def train(x_train, y_train, x_test, y_test, batch_size= 64, epochs = 100):

    inputs = Input(shape=x_train.shape[1:])
    x = Conv2D(8, kernel_size=(7, 7), strides=(1, 1), padding='same')(inputs)
    x = fake_clip()(x)
    x = ReLU()(x)
    x = MaxPool2D((4, 4),strides=(4, 4), padding="same")(x)

    # dense block
    x = dense_block(x, k=24)

    # bottleneck -1
    #x = Conv2D(32, kernel_size=(1, 1), strides=(1, 1), padding='same')(x)
    #x = fake_clip()(x)
    #x = ReLU()(x)
    #x = MaxPool2D((2, 2), strides=(2, 2), padding="same")(x)

    # dense block -2
    #x = dense_block(x, k=12)

    #x = Conv2D(10, kernel_size=(1, 1), strides=(1, 1), padding='same')(x)
    #x = fake_clip()(x)
    #x = ReLU()(x)

    # global avg.
    #x = GlobalAvgPool2D()(x)
    x = GlobalMaxPool2D()(x)

    '''
    # output
    #x = Flatten()(x)
    x = Dense(128)(x)
    x = fake_clip()(x)
    x = ReLU()(x)
    '''
    x = Dropout(0.2)(x)
    x = Dense(10)(x)
    x = fake_clip()(x)

    predictions = Softmax()(x)

    model = Model(inputs=inputs, outputs=predictions)

    model.compile(loss='categorical_crossentropy',
                  optimizer='adam',
                  metrics=['accuracy'])

    model.summary()

    # save best
    checkpoint = ModelCheckpoint(filepath=save_dir,
            monitor='val_acc',
            verbose=0,
            save_best_only='True',
            mode='auto',
            period=1)
    callback_lists = [checkpoint]

    history =  model.fit(x_train, y_train,
              batch_size=batch_size,
              epochs=epochs,
              verbose=2,
              validation_data=(x_test, y_test),
              shuffle=True, callbacks=callback_lists)

    # free the session to avoid nesting naming while we load the best model after.
    del model
    K.clear_session()
    return history


def main(weights='weights.h'):

    #os.environ["CUDA_VISIBLE_DEVICES"] = "-1"

    epochs = 5
    num_classes = 10

    # The data, split between train and test sets:
    (x_train, y_train), (x_test, y_test) = mnist.load_data()
    #(x_train, y_train), (x_test, y_test) = cifar10.load_data()

    print(x_train.shape[0], 'train samples')
    print(x_test.shape[0], 'test samples')

    # Convert class vectors to binary class matrices.
    y_train = to_categorical(y_train, num_classes)
    y_test = to_categorical(y_test, num_classes)

    # reshape to 4 d becaue we build for 4d?
    x_train = x_train.reshape(x_train.shape[0], x_train.shape[1], x_train.shape[2], 1)
    x_test = x_test.reshape(x_test.shape[0], x_test.shape[1], x_test.shape[2], 1)
    print('x_train shape:', x_train.shape)

    # quantize the range to q7 without bias
    x_test = np.clip(np.floor((x_test)/8), -128, 127)
    x_train = np.clip(np.floor((x_train)/8), -128, 127)

    print("data range", x_test.min(), x_test.max())

    if(os.getenv('NNOM_TEST_ON_CI') == 'YES'):
        shift_list = eval(open('.shift_list').read())
        rP = 0.0
        for i,im in enumerate(x_test):
            X = im.reshape(1,28,28,1)
            f2q(X, shift_list['input_1']).astype(np.int8).tofile('tmp/input.raw')
            if(0 == os.system('./mnist > /dev/null')):
                out = q2f(np.fromfile('tmp/Softmax1.raw',dtype=np.int8),7)
                out = np.asarray(out)
                num, prop = out.argmax(), out[out.argmax()]
                rnum = y_test[i].argmax()
                if((rnum == num) and (prop > 0.8)):
                    #print('test image %d is %d, predict correctly with prop %s'%(i, rnum, prop))
                    rP += 1.0
                if((i>0) and ((i%1000)==0)):
                    print('%.1f%%(%s) out of %s is correct predicted'%(rP*100.0/i, rP, i))
        print('%.1f%%(%s) out of %s is correct predicted'%(rP*100.0/i, rP, i))
        if(rP/i > 0.8):
            return
        else:
            raise Exception('test failed, accuracy is %.1f%% < 80%%'%(rP*100.0/i))

    # generate binary
    if(not os.path.exists('mnist_test_data.bin')):
        generate_test_bin(x_test, y_test, name='mnist_test_data.bin')

    # train model
    if(not os.path.exists(save_dir)):
        history = train(x_train,y_train, x_test, y_test, batch_size=128, epochs=epochs)
        acc = history.history['acc']
        val_acc = history.history['val_acc']
        if(os.getenv('NNOM_ON_CI') == None):
            plt.plot(range(0, epochs), acc, color='red', label='Training acc')
            plt.plot(range(0, epochs), val_acc, color='green', label='Validation acc')
            plt.title('Training and validation accuracy')
            plt.xlabel('Epochs')
            plt.ylabel('Loss')
            plt.legend()
            plt.show()
  
    # get best model
    model = load_model(save_dir)

    # evaluate
    evaluate_model(model, x_test, y_test)

    # convert to model on nnom
    generate_model(model, x_test[:10], name=weights)

    return model,x_train,y_train,x_test,y_test

if __name__ == "__main__":
    main()
