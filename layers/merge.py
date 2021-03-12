from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import tensorflow as tf

from tframe import console, checker, pedia
from tframe.layers.layer import Layer, single_input, Function
from tframe.utils import get_scale


class ShortCut(Layer):
  full_name = 'shortcut'
  abbreviation = 'shortcut'

  is_nucleus = False

  class Mode:
    SUM = 'sum'
    CONCATE = 'concate'

  @property
  def structure_tail(self):
    return '({})'.format(','.join(self.transformation_str_list))

  @property
  def transformation_str_list(self):
    result = []
    if self._transforms is None:
      return [f.output_id_str for f in self.definitions]
    for f, t_list in zip(self.definitions, self._transforms):
      result.append(
        '->'.join([f.output_id_str] + [t.group_name for t in t_list]))
    return result

  def __init__(self, *definitions, axis=-1, mode='concate', transforms=None):
    if len(definitions) == 0:
      console.warning_with_pause('Nothing to be merged.')
    self.definitions = checker.check_type(definitions, Function)
    for f in self.definitions: f.set_output_id()
    self.axis = axis
    # Check mode
    assert mode in (self.Mode.SUM, self.Mode.CONCATE)
    self.mode = mode
    self.full_name = mode
    self.abbreviation = mode
    # Check transforms
    if transforms is not None:
      assert isinstance(transforms, list)
      assert len(transforms) == len(self.definitions)
      for t in transforms: checker.check_type(t, Function)
    self._transforms = transforms

  @single_input
  def _link(self, input_, **kwargs):
    assert isinstance(input_, tf.Tensor)
    if len(self.definitions) == 0: return input_
    # Get tensor list to merge
    tensors = [input_]
    if self._transforms is None:
      tensors += [f.output_tensor for f in self.definitions]
    else:
      for i, (f, t_list) in enumerate(zip(self.definitions, self._transforms)):
        y = f.output_tensor
        for j, t in enumerate(t_list):
          with tf.variable_scope('{}-{}'.format(i, j)): y = t(y)
        tensors.append(y)
    # Merge
    if self.mode == self.Mode.CONCATE: return tf.concat(tensors, axis=self.axis)
    elif self.mode == self.Mode.SUM: return tf.add_n(tensors)
    else: raise NotImplementedError

  def add_transformation(self, f, branch_id=0):
    assert isinstance(f, Function)
    if getattr(f, 'is_nucleus', False): self.is_nucleus = True
    # Initialize self._transform if necessary
    if self._transforms is None:
      self._transforms = [[] for _ in self.definitions]
    # Add f into transformation list
    self._transforms[branch_id].append(f)


class Merge(Layer):

  PROD = pedia.prod
  SUM = pedia.sum
  CONCAT = pedia.concat
  CONCAT_SUM = 'concat-sum'

  def __init__(self, merge_method, **kwargs):
    """This layer class provides some build-in merge method, including
    those listed in the class variables with capitalized names. When using
    `CONCAT_SUM` method, one needs to specify `sum_indices`. Other tensors
    will be concatenated first and added to those within `sum_indices`.
    Currently a more general design is not needed."""
    self.full_name, self.abbreviation = merge_method, merge_method
    self.merge_method = merge_method
    # Attributes for CONCAT method
    self._axis = kwargs.get('axis', -1)
    # Attributes for `CONCAT-SUM` method
    self._sum_indices = kwargs.get('sum_indices', (0,))
    if isinstance(self._sum_indices, int):
      self._sum_indices = (self._sum_indices,)
    if merge_method == self.CONCAT_SUM:
      self.full_name += '({})'.format(','.join(self._sum_indices))
    # Store other keyword arguments
    self.kwargs = kwargs

  def _link(self, *input_list, **kwargs):
    # Check input_list
    assert len(input_list) > 0
    if len(input_list) == 1: input_list = input_list[0]
    assert isinstance(input_list, (list, tuple)) and len(input_list) > 1

    # Merge according to specification
    if self.merge_method == self.SUM: return tf.add_n(input_list)
    elif self.merge_method == self.CONCAT:
      return tf.concat(input_list, axis=self._axis)
    elif self.merge_method == self.PROD:
      output = input_list.pop()
      for tensor in input_list: output *= tensor
      return output
    elif self.merge_method == self.CONCAT_SUM:
      assert len(input_list) > 2
      assert 0 < len(self._sum_indices) <= len(input_list) - 2
      y = tf.concat([x for i, x in enumerate(input_list)
                     if i not in self._sum_indices], axis=self._axis)
      inputs = [x for i, x in enumerate(input_list) if i in self._sum_indices]
      inputs.append(y)
      return tf.add_n(inputs)
    else: raise KeyError('!! Unknown merge method {}'.format(self.merge_method))

  @classmethod
  def Sum(cls):
    return Merge(cls.SUM)

  @classmethod
  def Prod(cls):
    return Merge(cls.PROD)

  @classmethod
  def Concat(cls, axis=-1):
    return Merge(cls.CONCAT, axis=axis)

  @classmethod
  def ConcatSum(cls, sum_indices=(0,)):
    return Merge(cls.CONCAT_SUM, sum_indices=sum_indices)


class ConcatenateForGAN(Layer):
  full_name = 'concatenate'
  abbreviation = 'concat'

  def __init__(self, companions=None):
    """
    Initiate a concatenate layer
    :param companions: a dictionary with format:
                       {tensor0: insert_position0, ..., 
                        tensorN: insert_positionN}
                        companion tensors will be inserted into input list
                        at the specific position
    """
    # Check companion
    if companions is not None:
      for key in companions.keys():
        if not isinstance(key, tf.Tensor):
          raise TypeError('key must be a tensor')
        if not isinstance(companions[key], int):
          raise TypeError('value must be an integer')

    self._companions = companions

  def _link(self, inputs, **kwargs):
    if isinstance(inputs, tf.Tensor):
      inputs = [inputs]

    # Avoid that insert operation below changes the original list
    inputs = inputs.copy()

    assert isinstance(inputs, list)
    if not self._companions is None:
      for tensor in self._companions.keys():
        assert isinstance(tensor, tf.Tensor)
        inputs.insert(self._companions[tensor], tensor)

    # Check inputs
    if len(inputs) < 2:
      raise ValueError('inputs to concatenate layer must have a length'
                        ' larger than 1')

    # Prepare inputs for concatenation
    assert isinstance(inputs[0], tf.Tensor)
    leader_shape_tensor = tf.shape(inputs[0])
    leader_shape = inputs[0].get_shape().as_list()

    for i in range(1, len(inputs)):
      assert isinstance(inputs[i], tf.Tensor)
      shape = inputs[i].get_shape().as_list()
      shape_tensor = tf.shape(inputs[i])
      ones = tf.ones(
        [leader_shape_tensor[0]] + leader_shape[1:-1] + [shape[-1]])

      target_shape = ([shape_tensor[0]] + [1]*(len(leader_shape) - 2)
                      + [shape[-1]])
      reshaped = tf.reshape(inputs[i], target_shape)

      inputs[i] = reshaped * ones

    result = tf.concat(inputs, axis=len(leader_shape) - 1)
    self.neuron_scale = get_scale(result)
    return result






