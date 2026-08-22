A newly created user starts with is_verified=False. When they successfully authenticate with a valid OTP sent to their phone, the phone is considered verified and is_verified becomes True, if teh user sign up and dont verify its phone number and the phone number is not there own and the real owner of that phone number try to sign up the un verify row of taht phone number will be deleted so if a user take some one else phone number by accident adn put there own first and last name for it they cant verify it because they dont recive otp and when teh real owner of taht phone number try to sign up the old data that have the old first adn last naem get delete and new row created and this delete happend at teh validation.py code for phone number valiation

user can have multiple device and if tehy are un active for 30 days that device get deleted automaticly for keeping the user active sessions limited to the devices he use requealy

session will be remove after logout and new sessions only crated at the login, after each login the user last_log_in get updated and after each access token renewal the session last_activity_at get updated

