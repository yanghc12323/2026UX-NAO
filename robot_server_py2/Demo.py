from naoqi import ALProxy
import time


def bow_action():
    names_bow = ["LHipPitch",   
                 "RHipPitch",
                 "HeadPitch"]
    angles_bow = [
        -0.65,  # 左髋部俯仰（弯腰）
        -0.65,  # 右髋部俯仰（弯腰）
        0.3#  头部稍微低下
    ]
    # set the angles and wait for the action finish
    # motion_service.setAngles("HeadPitch", 0.0, 0.5)  # Let head go up a little
    times_handsClose = [0.5] * 10
    times_bow = [1.5] * 3
    is_absolute = True

    # bow
    motion_service.angleInterpolation(names_bow, angles_bow, times_bow, is_absolute)

    # keep the posture for a while
    time.sleep(0.5)


def lying_action():
    posture.goToPosture("LyingBelly", 0.3)  # 趴下
    time.sleep(1)
    posture.goToPosture("Crouch", 0.5)  # 回复


def talking():
    tts.setLanguage("Chinese")
    content="你好"  #替换为所需的字符
    tts.say(content)


def rest():
    motion_service.rest()



def main():
 
    bow_action()
    time.sleep(1)

    lying_action()
    time.sleep(1)

    talking()
    time.sleep(1)

    rest() #使NAO回到静息态



if __name__ == "__main__":
    # 一些全局变量定义

    # NAO初始化
    robot_ip = "192.168.93.152"  #NAO报的ip
    robot_port = 9559  #自己电脑的空闲端口

    # set parameters
    motion_service = ALProxy("ALMotion", robot_ip, robot_port)
    posture = ALProxy("ALRobotPosture", robot_ip, robot_port)
    tts = ALProxy("ALTextToSpeech", robot_ip, robot_port)

    motion_service.wakeUp()  #必须！使NAO从静息态苏醒
    motion_service.setStiffnesses("Body", 1.0)  #设置身体刚度

 
    # 运行主体程序
    main()

