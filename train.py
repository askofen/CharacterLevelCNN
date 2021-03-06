import math
import os
import tensorflow as tf

from helpers.file_helper import FileHelper
from neural_network import cnn
from encoders.encode_helper import EncodeHelper
from helpers.preprocess_helper import PreprocessHelper
from neural_network.cnn import CNNRunner


# run tensorboard:
# tensorboard --logdir=log

# Initialize variables
VERBOSE = False

alphabet_size = 0

use_whole_dataset = os.getenv('USE_WHOLE_DATASET', 'False').lower() == "true"
data_path = os.getenv('DATA_PATH', 'data/encoded')

# current options: 'standard', 'standard_group', 'ascii', 'ascii_group'
encoding_name = os.getenv('ENCODING_NAME', 'ascii_group')
output_postfix = os.getenv('OUTPUT_POSTFIX', 'example_run')
output_folder = os.getenv('OUTPUT_FOLDER', 'output')
restore_checkpoint_path = os.getenv('RESTORE_CHECKPOINT_PATH', '')

extended_mode = os.getenv('EXTENDED_MODE', 'False').lower() == "true"


if encoding_name == "standard":
    alphabet_size = len(EncodeHelper.alphabet_standard)
elif encoding_name == "standard_group":
    alphabet_size = len(EncodeHelper.make_standart_group_encoding()['a'])
elif encoding_name == "ascii":
    alphabet_size = len(EncodeHelper.make_ascii_encoding()['a'])
elif encoding_name == "ascii_group":
    alphabet_size = len(EncodeHelper.make_ascii_group_encoding()['a'])

full_output_name = "{}_{}".format(encoding_name, output_postfix)

epochs = int(os.getenv('EPOCHS_COUNT', 1000))
batch_size = int(os.getenv('BATCH_SIZE', 100))
train_eval_batch_size = int(os.getenv('TRAIN_EVAL_BATCH_SIZE', 1000))

learning_rate = float(os.getenv('LEARNING_RATE', 0.0001))
dropout = float(os.getenv('DROPOUT_RATE', 0.25))

eval_mode = os.getenv('EVAL_MODE', 'default')
mode_str = os.getenv('RUN_MODE', 'train')
mode = tf.estimator.ModeKeys.TRAIN if mode_str == 'train' else tf.estimator.ModeKeys.EVAL

# Load data
train_messages = []
train_scores = []
test_messages = []
test_scores = []

log_file_name = mode_str

if mode == tf.estimator.ModeKeys.TRAIN:
    test_messages, test_scores = PreprocessHelper.get_encoded_messages(
        "{}/{}/test/Beauty_test_13862.json.pickle".format(data_path, encoding_name))

    if use_whole_dataset:
        train_messages, train_scores = PreprocessHelper.get_encoded_messages_from_folder(
            "{}/{}/train".format(data_path, encoding_name))
    else:
        train_messages, train_scores = PreprocessHelper.get_encoded_messages(
            "{}/{}/train/Beauty_train_32343.json.pickle".format(data_path, encoding_name))

if mode == tf.estimator.ModeKeys.EVAL:
    if use_whole_dataset:
        test_messages, test_scores = PreprocessHelper.get_encoded_messages_from_folder(
            "{}/{}/test".format(data_path, encoding_name))
    else:
        test_messages, test_scores = PreprocessHelper.get_encoded_messages(
            "{}/{}/test/Beauty_test_13862.json.pickle".format(data_path, encoding_name))

    if mode_str != 'default':
        log_file_name = "{}_{}_v2".format(log_file_name, eval_mode)

# logging
logger = FileHelper.get_file_console_logger(full_output_name, output_folder, "{}.log".format(log_file_name), True)


# Initialize graph
tf.reset_default_graph()
tf.set_random_seed(111)

# Initialize inputs
eval_results = {"sum": 0, "count": 0, "predicted": [], "actual": []}
is_train = tf.Variable(True)

y = tf.placeholder(tf.float32, [None], name="y")
y_batch = tf.reshape(y, [-1, 1], name="y_batch")
x_batch = tf.placeholder(tf.float32, [None, 1024, alphabet_size], name="x_batch")

x_batch_4 = tf.reshape(x_batch, [-1, 1024, alphabet_size, 1])
x_batch_input = tf.transpose(x_batch_4, perm=[0, 2, 1, 3])

# Convolutional-max pool 1
layer1_filters = 128
if extended_mode:
    layer1_filters = layer1_filters * 9

conv1_layer = cnn.cnn_conv_layer(x_batch_input, name="1",
                                 filter_shape=[alphabet_size, 5], filters=layer1_filters, channels=1)
pool1_layer = cnn.max_pooling(conv1_layer, "1", pool_shape=[1, 5])

if VERBOSE:
    pool1_layer = tf.Print(pool1_layer, [conv1_layer, pool1_layer],
                           message="This is conv1_layer, pool1_layer: ")

# Convolutional-max pool 2
conv2_layer = cnn.cnn_conv_layer(pool1_layer, name="2",
                                 filter_shape=[1, 5], filters=256, channels=layer1_filters)
pool2_layer = cnn.max_pooling(conv2_layer, "2", pool_shape=[1, 5])

if VERBOSE:
    pool2_layer = tf.Print(pool2_layer, [conv2_layer, pool2_layer],
                           message="This is conv2_layer, pool2_layer: ")

# Convolutional-max pool 3
conv3_layer = cnn.cnn_conv_layer(pool2_layer, name="3",
                                 filter_shape=[1, 3], filters=512, channels=256)
pool3_layer = cnn.max_pooling(conv3_layer, "3", pool_shape=[1, 3])

if VERBOSE:
    pool3_layer = tf.Print(pool3_layer, [conv3_layer, pool3_layer],
                           message="This is conv3_layer, pool3_layer: ")

# Full connection
# flat_layer = cnn.make_flat(pool2_layer)
flat_layer = cnn.make_flat(pool3_layer)
dropout_layer1 = tf.layers.dropout(flat_layer, rate=dropout, training=is_train)
full_connected1 = cnn.full_connection(dropout_layer1, count_neurons=500, name="1")
dropout_layer2 = tf.layers.dropout(full_connected1, rate=dropout, training=is_train)
full_connected2 = cnn.full_connection(dropout_layer2, count_neurons=100, name="2")
dropout_layer3 = tf.layers.dropout(full_connected2, rate=dropout, training=is_train)
full_connected3 = cnn.full_connection(dropout_layer3, count_neurons=1, name="3")

if VERBOSE:
    full_connected3 = tf.Print(full_connected3,
                               [full_connected1, full_connected2, full_connected3],
                               message="This is full_connected 1,2,3: ")

# Optimization
diff = tf.subtract(full_connected3, y_batch)
error = tf.square(diff)
error_sum = tf.reduce_sum(error)

mean_square_error = tf.reduce_mean(error)
root_mean_square_error = tf.sqrt(mean_square_error)

optimiser = tf.train.AdamOptimizer(learning_rate=learning_rate).minimize(error)

# Run
saver = tf.train.Saver()

config = tf.ConfigProto(log_device_placement=VERBOSE)
config.gpu_options.allow_growth = True

runner = CNNRunner(VERBOSE, batch_size, logger)

with tf.Session(config=config) as sess:
    def run_train(start_index, end_index, epoch_num, messages, scores):
        is_train.load(True, sess)
        sess.run(optimiser, feed_dict={x_batch: messages[start_index:end_index],
                                       y: scores[start_index:end_index]})

        is_train.load(False, sess)
        batch_rmse = sess.run(root_mean_square_error, feed_dict={x_batch: messages[start_index:end_index],
                                                                 y: scores[start_index:end_index]})
        logger.info("Train Epoch {}, Batch {} - {}: RMSE = {}".format(epoch_num, start_index, end_index, batch_rmse))

    def run_eval(start_index, end_index, epoch_num, messages, scores):
        is_train.load(False, sess)
        squared_error_sum, predicted = sess.run([error_sum, full_connected3],
                                                feed_dict={x_batch: messages[start_index:end_index],
                                                y: scores[start_index:end_index]})
        count = end_index - start_index

        eval_results["sum"] = eval_results["sum"] + squared_error_sum
        eval_results["count"] = eval_results["count"] + count
        eval_results["predicted"].extend(predicted)
        eval_results["actual"].extend(scores[start_index:end_index])

        batch_rmse = math.sqrt(squared_error_sum/count)

        logger.info("Eval Epoch {}, Batch {} - {}: RMSE = {}".format(epoch_num, start_index, end_index, batch_rmse))


    sess.run(tf.global_variables_initializer())

    if restore_checkpoint_path:
        saver.restore(sess, restore_checkpoint_path)

    if mode == tf.estimator.ModeKeys.TRAIN:
        writer = tf.summary.FileWriter('{}/graph/{}/'.format(output_folder, full_output_name), sess.graph)
        checkpoints_dir = "{}/checkpoints/{}".format(output_folder, full_output_name)

        if not os.path.exists(checkpoints_dir):
            os.makedirs(checkpoints_dir)

        for epoch in range(epochs):
            runner.call_for_each_batch(epoch, run_train, train_messages, train_scores)
            saver.save(sess, "{}/model_epoch{}.ckpt".format(checkpoints_dir, epoch))
            run_eval(0, train_eval_batch_size, epoch)

        writer.close()

    if mode == tf.estimator.ModeKeys.EVAL:
        if eval_mode == "default":
            runner.call_for_each_batch(0, run_eval, test_messages, test_scores)
            total_rmse = math.sqrt(eval_results["sum"] / eval_results["count"])
            logger.info("Eval Total RMSE = {}".format(total_rmse))

            eval_score_dir = "{}/eval/{}/score.json".format(output_folder, full_output_name)
            FileHelper.write_predictions_to_file(eval_score_dir, eval_results["predicted"], eval_results["actual"])
        elif eval_mode == "bootstrap":
            bootstraps = PreprocessHelper.bootstrap_test_indexes()
            for iteration in range(len(bootstraps)):
                indexes = bootstraps[iteration]
                sample_messages, sample_scores = runner.get_subset(test_messages, test_scores, indexes)
                runner.call_for_each_batch(iteration, run_eval, sample_messages, sample_scores)
                total_mse = eval_results["sum"] / eval_results["count"]
                logger.info("Iteration {}, Eval Total MSE = {}".format(iteration, total_mse))
