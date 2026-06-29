"""This is an example of how to compute the transform from the iPhone frame to the TCP frame for the iPhone 15 Pro using the provided mount."""

import numpy as np

IPHUMI_TCP_OFFSET_FROM_MAIN_CAMERA = [0, -0.06441, -0.211397] # specific to the provided iPhone 15 Pro mount. in ARKit main camera coordinate system (optical center of main camera); geometrically is the position of the TCP frame in the ARKit frame. 0 for x here means that the main camera is centered on the gripper.

# the iPhone pose is the pose of the optical center of the main camera on the iPhone with respect to the world frame. With the iPhone in landscape mode (screen facing you), with the charging port to the right, the x-axis points to the right, the y-axis points up, and the z-axis points towards the user.
# the tcp pose is the pose at the end of the gripper in the middle vertically and horizontally of the fingers. When holding the gripper in your hand, z points away from you, x points to the right, and y points down
# thus to convert from iPhone pose to TCP pose, we need both a rotation and a translation
# the rotation consists of a rotation to account for mount angle (15 degrees) and a rotation from arkit convention to TCP
mount_rotation = np.array([[1,0,0],
                            [0,np.cos(np.deg2rad(15)),-np.sin(np.deg2rad(15))],
                            [0,np.sin(np.deg2rad(15)),np.cos(np.deg2rad(15))]])
arkit_tcp_rot = np.array([[1,0,0],
                            [0,-1,0],
                            [0,0,-1]])
iphone_tcp_rot = mount_rotation @ arkit_tcp_rot

# iphone_poses is geometrically the pose of the iPhone frame in the world frame (W_T_I)

# I_T_TCP is geometrically the pose of the TCP frame in the iPhone ARKit frame; involves a 180 rotation about X axis and a translation. For iPhone 15 Pro
I_T_TCP = np.array([[0,0,0,0],
                    [0,0,0,0],
                    [0,0,0,0],
                    [0,0,0,1]], dtype=np.float32)
I_T_TCP[:3,:3] = iphone_tcp_rot
I_T_TCP[:3,3] = IPHUMI_TCP_OFFSET_FROM_MAIN_CAMERA

print(I_T_TCP)
