from termcolor import colored

ALPACA_IMAGE = r"""
              04515                                           # # #
              2 52 3     x               x                       #   #
             1473173    x x             x x                       #   #
         75   44   2     x               x                        #   #
          41       13                                            #   #
              3    13           x                             # # #
   x          3     5          x x                      #
  x x        27     17          x             x        # #
   x        72      17                       x x     #     #
            75      11                        x     #       #         x
            3        464455444451                 #           #      x x
            2         27771771132  13            #             #      x
            2         3 73 37 5 37 715         #                 #
            2         3        711 7137       #                   #
            3         353435225157 735      #         OASIS         #
            12                     71      #           LMF           #
              3            732665  71    #                             #
               71  227 27   5  32  71   #                               #
               73  317 4    4  13  17 #                                   #
                3  317 4    4 713  2 #                                     #
                2  33772    4 713  4
                2 27371     4 373 17
                2 4 272     435 2 2
"""


def print_alpaca():
    print(colored(ALPACA_IMAGE, "yellow"))
