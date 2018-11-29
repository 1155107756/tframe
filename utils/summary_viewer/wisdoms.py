from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import numpy as np


WISDOMS_WITH_QUOTES = (
  ('Believe and act as if it were impossible to fail.',
   'Charles F. Kettering'),
  ('Guard well your thoughts when alone and your words when accompanied',
   'Roy T. Bennett'),
  ("Courage is't having the strength to go on. "
   "It's going on when you don't have strength.",
   'Napoleon'),
  ("A true hero isn't measured by the size of his strength, "
   "but by the strength of his heart",
   '<Hercules>'),
  ("The greater the obstacle, the more glory in overcoming it.",
   "Moliere"),
)


def rand_wisdom():
  wisdom, quote = WISDOMS_WITH_QUOTES[
    np.random.randint(len(WISDOMS_WITH_QUOTES))]
  return '{}    — {}'.format(wisdom, quote)


