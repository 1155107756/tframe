from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import six
import numpy as np
import tensorflow as tf
import tframe as tfr
from tframe.core.quantity import Quantity

from . import losses


def _truncate(truth, output):
  # TODO: only supported for some metrics
  assert len(truth.shape.as_list()) > 2
  i = tf.cond(tf.get_collection(tfr.pedia.is_training)[0],
              lambda: 0, lambda: tfr.hub.val_preheat)
  return truth[:, i:], output[:, i:]


# region : General Metrics

def accuracy(truth, output, pred_thres=None):
  """
  labels are provided by data_set, outputs are generated by model
  For FNN, outputs.shape = (batch, [*sample_shape], num_classes)
  For RNN, outputs.shape = (batch, num_steps, num_classes)

  :param pred_thres: The prediction threshold.
  """
  # Truncate data if necessary TODO: maybe its not safe
  # RNN outputs usually have a dimension larger than 2
  if len(truth.shape) > 2 and tfr.hub.val_preheat > 0:
    truth, output = _truncate(truth, output)

  # Convert labels and outputs to 2-D dense tensors
  tensors = [truth, output]
  for i, tensor in enumerate(tensors):
    shape = tensor.shape.as_list()
    # RNN outputs has a shape length of 3
    # Image segmentation results have a shape of 4 dims
    # assert len(shape) in (2, 3, 4)
    # Convert one-hot to dense if necessary
    if shape[-1] > 1:
      # tensor = tf.argmax(tensor, -1, name='labels' if i == 0 else 'predictions')
      tensor = tf.argmax(tensor, -1, output_type=tf.int32)
      tensor = tf.expand_dims(tensor, -1)
    # Put tensor back to list
    tensors[i] = tensor
    if pred_thres is None:
      tensors[i] = tf.round(tensor, name='labels' if i == 0 else 'predictions')

  # Prepare quantities
  if pred_thres is None:
    correct_prediction = tf.equal(tensors[0], tensors[1])
  else:
    assert pred_thres > 0
    abs_delta = tf.abs(tensors[0] - tensors[1])
    correct_prediction = tf.greater_equal(pred_thres, abs_delta)
  correct_prediction = tf.cast(correct_prediction, tfr.hub.dtype)
  return correct_prediction

def generalized_accuracy(truth, output):
  """This metric is first designed for ERG data set, for whom models are
     built with outputs of shape [1, string_len, symbol_number]"""
  # Sanity check
  truth_shape = truth.shape.as_list()
  output_shape = output.shape.as_list()
  assert len(truth_shape) == len(output_shape) == 3
  assert truth_shape[-1] == output_shape[-1] > 1

  # Compare distribution
  # TODO: consider tf.nn.top_k or something
  tf_sort = lambda val: tf.contrib.framework.sort(
    val, axis=2, direction='DESCENDING')

  alpha = tf.reduce_sum(tf.multiply(truth, output), axis=2)
  beta = tf.reduce_sum(tf.multiply(tf_sort(truth), tf_sort(output)), axis=2)

  metric_foreach = tf.cast(tf.equal(alpha, beta), tf.float32)
  return metric_foreach

# endregion : General Metrics

# region : Metrics for FNN only

def delta(truth, output):
  assert isinstance(truth, tf.Tensor) and isinstance(output, tf.Tensor)
  if tfr.hub.val_preheat > 0:
    truth, output = _truncate(truth, output)
  return tf.subtract(truth, output)

def norm_error_ratio(truth, output):
  assert isinstance(truth, tf.Tensor) and isinstance(output, tf.Tensor)
  if tfr.hub.val_preheat > 0:
    truth, output = _truncate(truth, output)
  return tf.norm(truth - output) / tf.norm(truth) * 100

def rms(x): return tf.sqrt(tf.reduce_mean(tf.square(x)))

def rms_error_ratio(truth, output):
  assert isinstance(truth, tf.Tensor) and isinstance(output, tf.Tensor)
  # TODO: pilot, tfr.hub.val_preheat > 0 only happens in RNN model
  #       thus output.shape is [batch_size, step_num, *target_shape]
  if tfr.hub.val_preheat > 0:
    truth, output = _truncate(truth, output)
  return rms(truth - output) / rms(truth) * 100

# endregion : Metrics for FNN only

# region : Quantities

def cohens_kappa():
  "Cohen's kappa for classdification tasks"
  num_classes = tfr.hub.num_classes
  assert isinstance(num_classes, int) and num_classes > 1
  def tf_summ_method(tensor):
    assert isinstance(tensor, tf.Tensor)
    shape = tensor.shape.as_list()
    assert shape[-1] == 2
    if not len(shape) == 2: tensor = tf.reshape(tensor, [-1, 2])
    return tf.constant(-1.0)
  def np_summ_method(x):
    from sklearn.metrics import cohen_kappa_score
    # Check input x
    assert isinstance(x, np.ndarray) and x.shape[-1] == 2
    if not len(x.shape) == 2: x = x.reshape(-1, 2)
    return cohen_kappa_score(x[:, 0], x[:, 1])
  return Quantity(Quantity.concate_dense_label_pred, tf_summ_method,
                  np_summ_method, name='Kappa', lower_is_better=False)

def f1_score():
  """F1 score for classification tasks"""
  num_classes = tfr.hub.num_classes
  assert isinstance(num_classes, int) and num_classes > 1
  def tf_summ_method(tensor):
    assert isinstance(tensor, tf.Tensor)
    shape = tensor.shape.as_list()
    assert shape[-1] == 2
    if not len(shape) == 2: tensor = tf.reshape(tensor, [-1, 2])
    F1s = []
    # Assume the prediction axis is on the left in confusion matrix
    for c in range(num_classes):
      col = tf.boolean_mask(tensor, tf.equal(tensor[:, 0], c))[:, 1]
      row = tf.boolean_mask(tensor, tf.equal(tensor[:, 1], c))[:, 0]
      TP = tf.count_nonzero(tf.equal(col, c), dtype=tf.int32)
      FP = tf.size(row) - TP
      FN = tf.size(col) - TP
      precision = TP / (TP + FP)
      recall = TP / (TP + FN)
      F1 = 2 * precision * recall / (precision + recall)
      F1s.append(tf.cond(tf.is_nan(F1),
                         lambda: tf.constant(0, dtype=tf.float64), lambda: F1))
    return tf.reduce_mean(F1s)

  def np_summ_method(x):
    assert isinstance(x, np.ndarray) and x.shape[-1] == 2
    if not len(x.shape) == 2: x = x.reshape(-1, 2)
    F1s = []
    # Assume the prediction axis is on the left in confusion matrix
    for c in range(num_classes):
      col, row = x[x[:, 0] == c][:, 1], x[x[:, 1] == c][:, 0]
      TP = len(col[col == c])
      assert TP == len(row[row == c])
      if TP == 0:
        F1s.append(0)
        continue
      FP, FN = len(row) - TP, len(col) - TP
      precision = TP / (TP + FP)
      recall = TP / (TP + FN)
      F1 = 2 * precision * recall / (precision + recall)
      F1s.append(F1)
    return np.mean(F1s)
  return Quantity(Quantity.concate_dense_label_pred, tf_summ_method,
                  np_summ_method, name='F1', lower_is_better=False)

# endregion : Quantities


def get(identifier, last_only=False, pred_thres=None, **kwargs):
  """This method is only used in predictor.build currently.
     Other usage has been deprecated."""
  if isinstance(identifier, Quantity): return identifier
  elif callable(identifier):
    # Metrics got in this way do not support batch validation
    return Quantity(identifier)

  elif isinstance(identifier, six.string_types):
    name = identifier
    identifier = identifier.lower()
    kernel, tf_summ_method, np_summ_method = None, None, None
    lower_is_better = True
    use_logits = False

    if identifier in ['accuracy', 'acc', 'seq_acc', 'seq_accuracy']:
      kernel = lambda t1, t2: accuracy(t1, t2, pred_thres)
      tf_summ_method = tf.reduce_mean
      if identifier in ['seq_acc', 'seq_accuracy']: last_only = True
      lower_is_better = False
      name = 'Accuracy'
    elif identifier in ['f1', 'f1_score']: return f1_score()
    elif identifier in ['kappa']: return cohens_kappa()
    elif identifier in ['generalized_accuracy', 'gen_acc']:
      kernel, tf_summ_method = generalized_accuracy, tf.reduce_mean
      lower_is_better = False
      name = 'Accuracy'
    elif identifier in ['ppl', 'perplexity']:
      kernel = losses.cross_entropy
      tf_summ_method = lambda x: tf.exp(tf.reduce_mean(x))
      np_summ_method = lambda x: np.exp(np.mean(x))
      name = 'Perplexity'
      use_logits = True
    elif identifier in ['bpc', 'bit_per_character']:
      kernel = losses.cross_entropy_base2
      tf_summ_method = tf.reduce_mean
      name = 'BPC'
      use_logits = True
    elif identifier in ['mse', 'mae', 'wmse', 'wmae']:
      kernel = {'mse': losses.mean_squared_error,
                'mae': losses.mean_absolute_error,
                'wmse': losses.weighted_mse,
                'wmae': losses.weighted_mae}[identifier]
      tf_summ_method = tf.reduce_mean
      name = identifier.upper()
    elif identifier in ['delta', 'distance']:
      kernel, tf_summ_method = delta, tf.norm
      name = 'L2'
    elif identifier in ['ratio', 'norm_ratio']:
      # This metric does not support quantities
      kernel = norm_error_ratio
      name = 'Err %'
    elif identifier in ['rms_ratio']:
      # This metric does not support quantities
      kernel = rms_error_ratio
      name = 'RMS %'
    elif identifier in ['rms_mv']:
      kernel, tf_summ_method = delta, rms
      np_summ_method = lambda x: np.sqrt(np.mean(np.square(x)))
      name = 'RMS(mv)'
    else: raise ValueError('Can not resolve `{}`'.format(identifier))

    return Quantity(kernel, tf_summ_method, np_summ_method, last_only,
                    name=name, lower_is_better=lower_is_better,
                    use_logits=use_logits, **kwargs)
  else:
    raise TypeError('identifier must be a Quantity, function or a string')




