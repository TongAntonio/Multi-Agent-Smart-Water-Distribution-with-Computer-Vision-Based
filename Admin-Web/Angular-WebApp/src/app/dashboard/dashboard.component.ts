import { Component, OnInit } from '@angular/core';
import { AngularFirestore } from 'angularfire2/firestore';
import { AngularFireDatabase } from 'angularfire2/database';
import { AngularFireAuth } from 'angularfire2/auth';
import { Observable } from 'rxjs/Observable';
import * as firebase from 'firebase/app';

@Component({
  selector: 'app-dashboard',
  templateUrl: './dashboard.component.html',
  styleUrls: ['./dashboard.component.css']
})
export class DashboardComponent implements OnInit {
  title = 'app';
  user: Observable<firebase.User>;
  startHr: Observable<any>;
  startMin: Observable<any>;
  endHr: Observable<any>;
  endMin: Observable<any>;
  weight : Observable<any>;
  temperature : Observable<any>;
  humidity : Observable<any>;
  waterlevel : Observable<any>;
  
  mode:any;
  records$: Observable<any>;
  totalglass :number;
  totalMoney :number;
  totalUser :number;

   constructor(public afAuth: AngularFireAuth,private db: AngularFireDatabase) {
      this.afAuth.auth.signInAnonymously();
      this.user = this.afAuth.authState;
    }

  ngOnInit() {
    this.startHr = this.db.object('/setting/startHr').valueChanges();
    this.startMin = this.db.object('/setting/startMin').valueChanges();
    this.endHr = this.db.object('/setting/endHr').valueChanges();
    this.endMin = this.db.object('/setting/endMin').valueChanges();

    this.weight = this.db.object('/sensor/weight').valueChanges();
    this.temperature = this.db.object('/sensor/temperature').valueChanges();
    this.humidity = this.db.object('/sensor/humidity').valueChanges();
    this.waterlevel = this.db.object('/sensor/waterlevel').valueChanges();

    this.db.object('/setting/mode').valueChanges().subscribe(x=> this.mode = x);

    this.records$ = this.db.list<any>('/records').valueChanges(); 
    this.records$.subscribe(datas=>{ 
          var user : string[] = []; 
          this.totalglass = 0;
          this.totalMoney = 0;
          for (var i = 0; i < datas.length; i++) {
            var p = datas[i].split('|');
            var p0 = p[0];
            var p1 = +p[1];
            var p2 = +p[2];
            user.push(p0);
            this.totalglass++;
            this.totalMoney +=p1;
          }
          var unique = user.filter((v, i, a) => a.indexOf(v) === i); 
          this.totalUser =unique.length;
    });

  }
  setTime(newStartHr,newStartMin,newEndHr,newEndMin){
    this.db.object('/setting/startHr').set(newStartHr);
    this.db.object('/setting/startMin').set(newStartMin);
    this.db.object('/setting/endHr').set(newEndHr);
    this.db.object('/setting/endMin').set(newEndMin);
  }
  turnOnOff(){
    if(this.mode==0){
      this.db.object('/setting/mode').set(1);
    }else{
      this.db.object('/setting/mode').set(0);        
    }
  }
}


