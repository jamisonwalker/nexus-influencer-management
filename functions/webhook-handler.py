import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../')

from listener import app
from mangum import Mangum

handler = Mangum(app)
